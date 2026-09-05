import type { Operation, OperationState } from '$lib/types/api';
import {
  operationLoginExplanation,
  operationLoginSession,
  trackedLoginOperation,
  type LoginExplanation
} from '../utils/login-diagnostics';
import { operationIsTerminal } from '../utils/operations';
import { LatestRequestGate, type ApiBlobResult } from './client';

export interface LoginAttemptView {
  operationState: OperationState | null;
  terminal: boolean;
  sessionId: string | null;
  imageUrl: string;
  hint: string;
  explanation: LoginExplanation | null;
}

interface LoginAttemptDependencies {
  readOperation: (operationId: string, signal: AbortSignal) => Promise<Operation>;
  readQr: (sessionId: string, signal: AbortSignal) => Promise<ApiBlobResult>;
  changed: (view: LoginAttemptView) => void;
  terminal: (view: LoginAttemptView) => void;
  createImageUrl?: (blob: Blob) => string;
  revokeImageUrl?: (url: string) => void;
}

export function initialLoginAttemptView(): LoginAttemptView {
  return {
    operationState: null,
    terminal: false,
    sessionId: null,
    imageUrl: '',
    hint: '正在读取本次登录操作…',
    explanation: null
  };
}

/** Separate control and image lanes: even a stuck QR response cannot stop operation polling. */
export class LoginAttemptMonitor {
  private view = initialLoginAttemptView();
  private readonly operationRequest = new LatestRequestGate();
  private readonly qrRequest = new LatestRequestGate();
  private closed = false;

  constructor(
    private readonly accountId: string,
    private readonly operationId: string,
    private readonly dependencies: LoginAttemptDependencies
  ) {}

  private publish(update: Partial<LoginAttemptView>): void {
    this.view = { ...this.view, ...update };
    if (!this.closed) this.dependencies.changed({ ...this.view });
  }

  private clearImage(): void {
    if (this.view.imageUrl) {
      (this.dependencies.revokeImageUrl ?? URL.revokeObjectURL)(this.view.imageUrl);
      this.view = { ...this.view, imageUrl: '' };
    }
  }

  private resetQr(): void {
    this.qrRequest.cancel();
    this.clearImage();
  }

  async poll(): Promise<void> {
    if (this.closed || this.view.terminal) return;
    const result = await this.operationRequest.runIfIdle((signal) =>
      this.dependencies.readOperation(this.operationId, signal)
    );
    if (this.closed || this.view.terminal || result.status === 'superseded' || result.status === 'busy')
      return;
    if (result.status === 'rejected') {
      this.publish({ hint: '暂时无法读取本次登录操作；会重试状态读取，不会重新发起登录。' });
      return;
    }
    const operation = trackedLoginOperation(result.value, this.accountId, this.operationId);
    if (!operation) {
      this.resetQr();
      this.publish({ sessionId: null, hint: '操作关联无法确认，未读取二维码；请刷新任务记录。' });
      return;
    }
    if (operationIsTerminal(operation.state)) {
      // Terminal authority wins immediately, even if an image fetch never settles.
      this.resetQr();
      const explanation = operationLoginExplanation(operation);
      this.publish({
        operationState: operation.state,
        terminal: true,
        sessionId: operationLoginSession(operation),
        explanation,
        hint: explanation.detail
      });
      this.dependencies.terminal({ ...this.view });
      return;
    }
    const sessionId = operationLoginSession(operation);
    if (sessionId !== this.view.sessionId) this.resetQr();
    this.publish({
      operationState: operation.state,
      sessionId,
      hint: sessionId
        ? this.view.sessionId === sessionId
          ? this.view.hint
          : '已关联本次登录会话，正在等待二维码…'
        : '正在等待本次操作关联登录会话；不会借用其他会话的二维码。'
    });
    if (sessionId) void this.refreshQr(sessionId);
  }

  private async refreshQr(sessionId: string): Promise<void> {
    const result = await this.qrRequest.runIfIdle((signal) => this.dependencies.readQr(sessionId, signal));
    if (
      this.closed ||
      this.view.terminal ||
      this.view.sessionId !== sessionId ||
      result.status === 'superseded' ||
      result.status === 'busy'
    )
      return;
    if (result.status === 'rejected') {
      this.clearImage();
      this.publish({ hint: '暂时无法读取二维码；仍在检查本次登录操作状态。' });
      return;
    }
    const response = result.value;
    this.clearImage();
    if (response.blob) {
      try {
        const imageUrl = (this.dependencies.createImageUrl ?? URL.createObjectURL)(response.blob);
        this.publish({ imageUrl, hint: '请使用对应平台 App 扫码确认。' });
      } catch {
        this.publish({ hint: '二维码暂时无法显示；仍在检查本次登录操作状态。' });
      }
    } else {
      this.publish({
        hint:
          response.status === 410
            ? '二维码已失效，仍在确认本次操作的最终状态…'
            : '本次会话的二维码尚未可用，仍在检查登录操作状态…'
      });
    }
  }

  dispose(): void {
    this.closed = true;
    this.operationRequest.cancel();
    this.resetQr();
  }
}
