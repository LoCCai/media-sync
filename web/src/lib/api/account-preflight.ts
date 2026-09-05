import type { Account, LoginPreflight, LoginStatus } from '$lib/types/api';
import { loginPreflightDisposition } from '../utils/workbench';
import { LatestRequestGate } from './client';

export const LOGIN_PREFLIGHT_UNAVAILABLE = '暂时无法读取登录启动预检，请刷新本地状态后重试。';

type PreflightReadResult =
  | { kind: 'skipped' | 'superseded' }
  | { kind: 'fulfilled'; report: LoginPreflight }
  | { kind: 'failed'; message: string };

/** Readiness belongs to one selected local-state snapshot, never a later successful login. */
export class AccountPreflightReader {
  private readonly gate = new LatestRequestGate();

  constructor(
    private readonly readReport: (accountId: string, signal: AbortSignal) => Promise<LoginPreflight>
  ) {}

  async read(account: Account | null, status: LoginStatus | null): Promise<PreflightReadResult> {
    if (!account || loginPreflightDisposition(account, status) !== 'required') {
      this.invalidate();
      return { kind: 'skipped' };
    }
    const { id, platform } = account;
    const result = await this.gate.run((signal) => this.readReport(id, signal));
    if (result.status === 'superseded') return { kind: 'superseded' };
    if (
      result.status === 'rejected' ||
      !result.value ||
      typeof result.value !== 'object' ||
      result.value.account_id !== id ||
      result.value.platform !== platform
    ) {
      return { kind: 'failed', message: LOGIN_PREFLIGHT_UNAVAILABLE };
    }
    return { kind: 'fulfilled', report: result.value };
  }

  invalidate(): void {
    this.gate.cancel();
  }
}
