import { writable } from 'svelte/store';

export type OperatorPhase = 'checking' | 'anonymous' | 'authenticated' | 'error' | 'logout_unconfirmed';
export interface OperatorState {
  phase: OperatorPhase;
  epoch: number;
  code: string;
}

export class OperatorAuthError extends Error {
  constructor(
    readonly code: string,
    readonly status = 0
  ) {
    super(code);
    this.name = 'OperatorAuthError';
  }
}

type Transport = (path: string, init: RequestInit) => Promise<Response>;
const AUTH_ROOT = '/api/v1/operator-auth';
const CSRF = /^[A-Za-z0-9_-]{43}$/;
const RETURN_PATHS = new Set([
  '/accounts',
  '/subscriptions',
  '/contents',
  '/assets',
  '/library',
  '/jobs',
  '/settings',
  '/diagnostics'
]);

/** Never carry arbitrary query data or an external destination through login. */
export function operatorReturnPath(search: string): string | null {
  const parameters = new URLSearchParams(search);
  const destinations = parameters.getAll('return_to');
  return destinations.length === 1 && RETURN_PATHS.has(destinations[0]) ? destinations[0] : null;
}

interface SessionPayload {
  authenticated: boolean;
  csrf_token?: string;
  expires_in_seconds?: number;
}

/** One serialized cookie-writing auth lane; credentials and CSRF never enter the store. */
export class OperatorAuthController {
  private view: OperatorState = { phase: 'checking', epoch: 0, code: '' };
  private state = writable<OperatorState>(this.view);
  readonly subscribe = this.state.subscribe;
  private csrf = '';
  private intent = 0;
  private lane: Promise<unknown> = Promise.resolve();
  private sessionCheck: { intent: number; pending: Promise<boolean> } | null = null;
  private expiry: ReturnType<typeof setTimeout> | null = null;
  private requests = new Set<AbortController>();

  constructor(private transport: Transport = (path, init) => fetch(path, init)) {}

  get snapshot(): OperatorState {
    return this.view;
  }

  private publish(phase: OperatorPhase, code = ''): void {
    this.view = { ...this.view, phase, code };
    this.state.set(this.view);
  }

  private clear(phase: OperatorPhase, code = ''): number {
    this.intent += 1;
    this.csrf = '';
    if (this.expiry !== null) clearTimeout(this.expiry);
    this.expiry = null;
    for (const request of this.requests) request.abort();
    this.requests.clear();
    this.view = { phase, code, epoch: this.view.epoch + 1 };
    this.state.set(this.view);
    return this.intent;
  }

  private enqueue<T>(action: () => Promise<T>): Promise<T> {
    const next = this.lane.then(action, action);
    this.lane = next.catch(() => undefined);
    return next;
  }

  private async request(path: string, init: RequestInit = {}): Promise<unknown> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20_000);
    try {
      const response = await this.transport(`${AUTH_ROOT}/${path}`, {
        ...init,
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'error',
        headers: { Accept: 'application/json', ...init.headers },
        signal: controller.signal
      });
      if (response.status === 204) return null;
      const body: unknown = await response.json();
      if (!response.ok) {
        const detail = body && typeof body === 'object' ? (body as Record<string, unknown>).detail : null;
        const allowed = new Set([
          'operator_login_failed',
          'operator_login_rate_limited',
          'operator_origin_forbidden',
          'operator_host_forbidden',
          'operator_csrf_forbidden',
          'operator_auth_required'
        ]);
        throw new OperatorAuthError(
          typeof detail === 'string' && allowed.has(detail) ? detail : 'operator_request_failed',
          response.status
        );
      }
      return body;
    } catch (error) {
      if (error instanceof OperatorAuthError) throw error;
      throw new OperatorAuthError('operator_connection_failed');
    } finally {
      clearTimeout(timer);
    }
  }

  private async session(): Promise<SessionPayload> {
    const body = await this.request('session');
    if (!body || typeof body !== 'object') throw new OperatorAuthError('operator_session_invalid');
    const payload = body as SessionPayload;
    if (payload.authenticated === false) return { authenticated: false };
    if (
      payload.authenticated !== true ||
      typeof payload.csrf_token !== 'string' ||
      !CSRF.test(payload.csrf_token) ||
      !Number.isInteger(payload.expires_in_seconds) ||
      payload.expires_in_seconds! < 1 ||
      payload.expires_in_seconds! > 28_800
    ) {
      throw new OperatorAuthError('operator_session_invalid');
    }
    return payload;
  }

  private grant(payload: SessionPayload): void {
    if (!payload.authenticated) {
      this.clear('anonymous', 'operator_auth_required');
      return;
    }
    const notice = this.view.code === 'operator_csrf_forbidden' ? this.view.code : '';
    if (this.view.phase !== 'authenticated' || this.csrf !== payload.csrf_token) this.clear('checking');
    this.csrf = payload.csrf_token!;
    if (this.expiry !== null) clearTimeout(this.expiry);
    const epoch = this.view.epoch;
    this.expiry = setTimeout(
      () => this.rejectSession(epoch, 'operator_session_expired'),
      payload.expires_in_seconds! * 1000
    );
    this.publish('authenticated', notice);
  }

  checkSession(): Promise<boolean> {
    if (this.sessionCheck?.intent === this.intent) return this.sessionCheck.pending;
    const intent = this.intent;
    const pending = this.enqueue(async () => {
      if (intent !== this.intent) return false;
      try {
        const payload = await this.session();
        if (intent !== this.intent) return false;
        this.grant(payload);
        return payload.authenticated;
      } catch (error) {
        if (intent === this.intent) this.clear('error', this.errorCode(error));
        return false;
      }
    });
    this.sessionCheck = { intent, pending };
    void pending.finally(() => {
      if (this.sessionCheck?.pending === pending) this.sessionCheck = null;
    });
    return pending;
  }

  login(credential: string): Promise<boolean> {
    const intent = this.clear('checking');
    return this.enqueue(async () => {
      try {
        if (intent !== this.intent) return false;
        await this.request('login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ credential })
        });
        credential = '';
        if (intent !== this.intent) return false;
        const payload = await this.session();
        if (intent !== this.intent) return false;
        this.grant(payload);
        return payload.authenticated;
      } catch (error) {
        if (intent === this.intent) this.clear('error', this.errorCode(error));
        return false;
      } finally {
        credential = '';
      }
    });
  }

  logout(): Promise<boolean> {
    const intent = this.clear('checking');
    return this.enqueue(async () => {
      try {
        if (intent !== this.intent) return false;
        // Retry an uncertain logout by checking the cookie, without reopening the private tree.
        const payload = await this.session();
        if (intent !== this.intent) return false;
        if (payload.authenticated)
          await this.request('logout', {
            method: 'POST',
            headers: { 'x-media-sync-csrf': payload.csrf_token! }
          });
        if (intent !== this.intent) return false;
        this.clear('anonymous', 'operator_logged_out');
        return true;
      } catch {
        if (intent === this.intent) this.clear('logout_unconfirmed', 'operator_logout_unconfirmed');
        return false;
      }
    });
  }

  rejectSession(epoch: number, code = 'operator_auth_required'): void {
    if (epoch !== this.view.epoch || this.view.phase !== 'authenticated') return;
    this.clear(code === 'operator_csrf_forbidden' ? 'checking' : 'anonymous', code);
    if (code === 'operator_csrf_forbidden') void this.checkSession();
  }

  beginRequest(): {
    epoch: number;
    csrf: string;
    signal: AbortSignal;
    assertCurrent: () => void;
    finish: () => void;
  } {
    if (this.view.phase !== 'authenticated' || !this.csrf)
      throw new OperatorAuthError('operator_auth_required', 401);
    const epoch = this.view.epoch;
    const controller = new AbortController();
    this.requests.add(controller);
    return {
      epoch,
      csrf: this.csrf,
      signal: controller.signal,
      assertCurrent: () => {
        if (controller.signal.aborted || epoch !== this.view.epoch || this.view.phase !== 'authenticated')
          throw new DOMException('Session changed', 'AbortError');
      },
      finish: () => this.requests.delete(controller)
    };
  }

  dispose(): void {
    this.clear('anonymous');
  }
  private errorCode(error: unknown): string {
    return error instanceof OperatorAuthError ? error.code : 'operator_connection_failed';
  }
}

export const operatorAuth = new OperatorAuthController();
