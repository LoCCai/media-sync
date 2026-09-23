import { apiBlob, type ApiBlobResult } from './client';

export type NativeQrRelayState = 'waiting' | 'showing' | 'guidance';

export type NativeQrView = NativeQrRelayView;

export interface NativeQrRelayView {
  state: NativeQrRelayState;
  imageUrl: string;
  hint: string;
  /** Seconds since the last successful image, null when none has arrived yet. */
  ageSeconds: number | null;
}

export interface NativeQrDependencies {
  readQr: (signal: AbortSignal) => Promise<ApiBlobResult>;
  changed: (view: NativeQrRelayView) => void;
  createImageUrl?: (blob: Blob) => string;
  revokeImageUrl?: (url: string) => void;
  now?: () => number;
  /** Consecutive missing polls before platform guidance replaces the plain hint. */
  guidanceAfterMisses?: number;
}

export const NATIVE_QR_FRESH_SECONDS = 180;

export function initialNativeQrView(): NativeQrRelayView {
  return {
    state: 'waiting',
    imageUrl: '',
    hint: '正在等待原生登录二维码…请先在 /crawler/ 页面发起登录。',
    ageSeconds: null
  };
}

/**
 * Read-only viewer for the native crawler QR relay
 * (`/crawler/api/crawler/qrcode`). The relay is shared and accountless: this
 * monitor never starts a login, never retries one, and only distinguishes
 * "image present" from "not present (yet/expired)" plus honest guidance when
 * the relay stays empty long enough to suspect the platform login dialog.
 */
export class NativeQrRelayMonitor {
  private view = initialNativeQrView();
  private closed = false;
  private misses = 0;
  private lastShownAt: number | null = null;
  private readonly create: (blob: Blob) => string;
  private readonly revoke: (url: string) => void;
  private readonly now: () => number;
  private readonly guidanceAfterMisses: number;

  constructor(private readonly dependencies: NativeQrDependencies) {
    this.create = dependencies.createImageUrl ?? URL.createObjectURL;
    this.revoke = dependencies.revokeImageUrl ?? URL.revokeObjectURL;
    this.now = dependencies.now ?? Date.now;
    this.guidanceAfterMisses = dependencies.guidanceAfterMisses ?? 15;
  }

  private publish(update: Partial<NativeQrRelayView>): void {
    this.view = { ...this.view, ...update };
    if (!this.closed) this.dependencies.changed({ ...this.view });
  }

  private clearImage(): void {
    if (this.view.imageUrl) {
      this.revoke(this.view.imageUrl);
      this.view = { ...this.view, imageUrl: '' };
    }
  }

  private ageSeconds(): number | null {
    return this.lastShownAt === null ? null : Math.max(0, Math.round((this.now() - this.lastShownAt) / 1000));
  }

  private missingHint(): string {
    const age = this.ageSeconds();
    if (this.lastShownAt !== null && age !== null && age >= NATIVE_QR_FRESH_SECONDS) {
      return '二维码已超过 180 秒时效并消失；请重新发起登录后继续等待新码。';
    }
    return '尚未读取到二维码；请确认已在 /crawler/ 页面发起登录并等待登录框弹出。';
  }

  async poll(): Promise<void> {
    if (this.closed) return;
    let response: ApiBlobResult;
    try {
      response = await this.dependencies.readQr(new AbortController().signal);
    } catch {
      this.misses += 1;
      if (this.misses >= this.guidanceAfterMisses) {
        this.clearImage();
        this.publish({ state: 'guidance', hint: this.platformGuidance() });
      } else if (this.view.state !== 'guidance') {
        this.publish({ state: 'waiting', hint: '暂时无法读取二维码，将继续重试（不会重新发起登录）。' });
      }
      return;
    }
    if (this.closed) return;
    if (response.blob) {
      this.misses = 0;
      this.lastShownAt = this.now();
      this.clearImage();
      try {
        const imageUrl = this.create(response.blob);
        this.publish({ state: 'showing', imageUrl, hint: '请使用对应平台 App 扫码确认。' });
      } catch {
        this.publish({ state: 'waiting', hint: '二维码暂时无法显示；将继续重试读取。' });
      }
      return;
    }
    this.misses += 1;
    this.clearImage();
    if (this.misses >= this.guidanceAfterMisses) {
      this.publish({ state: 'guidance', hint: this.platformGuidance() });
      return;
    }
    this.publish({ state: 'waiting', hint: this.missingHint(), ageSeconds: this.ageSeconds() });
  }

  private platformGuidance(): string {
    return [
      '持续约 30 秒未读到二维码：平台可能未弹出登录框，或二维码元素加载失败（选择器超时）。',
      '抖音登录在上游自身即不建议扫码（滑块风控不稳），请改用账户页的 Cookie 粘贴校验；',
      '其他平台请回到 /crawler/ 页面确认登录框已出现，并查看该页日志区的具体失败原因。'
    ].join('');
  }

  dispose(): void {
    this.closed = true;
    this.clearImage();
  }
}

export function nativeQrRead(apiReader = apiBlob): (signal: AbortSignal) => Promise<ApiBlobResult> {
  return (signal: AbortSignal) => apiReader('/crawler/api/crawler/qrcode', { signal }, 8000);
}
