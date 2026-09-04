import type { Platform } from '$lib/types/api';

export const PLATFORM_META: Record<Platform, { name: string; short: string }> = {
  bili: { name: '哔哩哔哩', short: 'BILI' },
  xhs: { name: '小红书', short: 'XHS' },
  dy: { name: '抖音', short: 'DY' },
  ks: { name: '快手', short: 'KS' },
  wb: { name: '微博', short: 'WB' },
  tieba: { name: '贴吧', short: 'TB' },
  zhihu: { name: '知乎', short: 'ZH' }
};

const STATUS_LABELS: Record<string, string> = {
  authenticated: '已认证',
  authenticating: '认证中',
  awaiting_auth: '等待认证',
  cancelled: '已取消',
  claimed: '已领取',
  discovered: '已发现',
  downloaded: '已下载',
  downloading: '下载中',
  enabled: '已启用',
  expired: '已过期',
  exported: '已导出',
  fail: '失败',
  failed: '失败',
  failed_retryable: '可重试',
  failed_terminal: '终止失败',
  interrupted: '已中断',
  not_run: '未运行',
  paused: '已暂停',
  pass: '通过',
  pending: '准备中',
  queued: '排队中',
  required: '需要认证',
  retry_wait: '等待重试',
  running: '运行中',
  succeeded: '成功',
  unknown: '未认证',
  verified: '已校验',
  waiting_auth: '等待认证',
  waiting_user: '等待扫码'
};

export function statusLabel(status: string | null | undefined): string {
  if (!status) return '—';
  return STATUS_LABELS[status] ?? status;
}

export function statusTone(
  status: string | null | undefined
): 'success' | 'warning' | 'danger' | 'info' | '' {
  if (!status) return '';
  if (['authenticated', 'enabled', 'exported', 'succeeded', 'verified'].includes(status)) return 'success';
  if (['failed', 'failed_retryable', 'failed_terminal', 'interrupted'].includes(status)) return 'danger';
  if (['expired', 'required', 'retry_wait', 'unknown', 'waiting_auth', 'waiting_user'].includes(status)) {
    return 'warning';
  }
  if (['authenticating', 'claimed', 'downloading', 'pending', 'queued', 'running'].includes(status))
    return 'info';
  return '';
}

export function formatDate(value: string | null | undefined, fallback = '—'): string {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).format(date);
}

export function formatDateLong(value: string | null | undefined, fallback = '—'): string {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(date);
}

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value < 1024) return `${value} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let amount = value / 1024;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024;
    index += 1;
  }
  return `${amount >= 10 ? amount.toFixed(1) : amount.toFixed(2)} ${units[index]}`;
}

export function shortId(value: string | null | undefined): string {
  if (!value) return '—';
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

export function intervalLabel(seconds: number): string {
  if (seconds % 86400 === 0) return `${seconds / 86400} 天`;
  if (seconds % 3600 === 0) return `${seconds / 3600} 小时`;
  if (seconds % 60 === 0) return `${seconds / 60} 分钟`;
  return `${seconds} 秒`;
}

export function operationLabel(kind: string): string {
  return (
    {
      'account-login': '账户登录',
      'asset-download': '资产下载',
      'emby-export': '媒体库导出',
      'pipeline-run': '下载 / 导出 Worker',
      'scheduler-run': '订阅同步 Worker'
    }[kind] ?? kind
  );
}
