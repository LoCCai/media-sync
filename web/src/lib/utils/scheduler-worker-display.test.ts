import { describe, expect, it } from 'vitest';
import type { Operation, OperationKind } from '$lib/types/api';
import {
  schedulerWorkerNotice,
  schedulerWorkerStateLabel,
  schedulerWorkerSummary
} from './scheduler-worker-display';

function operation(result: unknown, patch: Partial<Operation> = {}): Operation {
  return {
    kind: 'scheduler-run',
    state: 'succeeded',
    result,
    ...patch
  } as Operation;
}

describe('scheduler worker control and Job outcome separation', () => {
  it('keeps a one-failed-terminal Job distinct from a succeeded worker without changing durable state', () => {
    const value = operation({ processed_count: 1, status_counts: { failed_terminal: 1 } });
    const before = JSON.stringify(value);
    expect(schedulerWorkerStateLabel(value.kind, value.state)).toBe('Worker 已完成');
    expect(schedulerWorkerNotice(value)).toMatchObject({ tone: 'danger', title: '采集任务失败' });
    expect(schedulerWorkerNotice(value)?.detail).toContain('Worker 完成不等于采集成功');
    expect(JSON.stringify(value)).toBe(before);
  });

  it.each([
    [{ failed_retryable: 1 }, 'danger', '采集任务失败'],
    [{ succeeded: 1, failed_terminal: 1 }, 'danger', '部分采集任务失败'],
    [{ succeeded: 1, failed_retryable: 1, waiting_auth: 1 }, 'danger', '部分采集任务失败'],
    [{ queued: 1 }, 'warning', '采集任务尚未完成'],
    [{ claimed: 1 }, 'warning', '采集任务尚未完成'],
    [{ running: 1 }, 'warning', '采集任务尚未完成'],
    [{ retry_wait: 1 }, 'warning', '采集任务尚未完成'],
    [{ waiting_auth: 1 }, 'warning', '采集任务尚未完成'],
    [{ waiting_user: 1 }, 'warning', '采集任务尚未完成'],
    [{ fenced: 1 }, 'warning', '采集任务尚未完成'],
    [{ succeeded: 1, waiting_user: 1 }, 'warning', '采集任务尚未完成'],
    [{ cancelled: 1 }, 'warning', '存在已取消的采集任务'],
    [{ succeeded: 1, cancelled: 1 }, 'warning', '存在已取消的采集任务'],
    [{ idle: 1 }, 'info', '本次没有 Job 完成记录'],
    [{}, 'info', '本次没有 Job 完成记录'],
    [{ succeeded: 0 }, 'info', '本次没有 Job 完成记录'],
    [{ succeeded: 1, idle: 1 }, 'warning', '仅部分处理结果报告 Job 完成']
  ])(
    'does not promote non-success/mixed/empty summary %j to successful capture',
    (status_counts, tone, title) => {
      const processed_count = Object.values(status_counts).reduce((sum, value) => sum + value, 0);
      const value = operation({ processed_count, status_counts });
      expect(schedulerWorkerSummary(value)).toEqual({ processed_count, status_counts });
      expect(schedulerWorkerNotice(value)).toMatchObject({ tone, title });
    }
  );

  it('only reports Job completion for the all-success case, never downloads or playback', () => {
    const value = operation({ processed_count: 2, status_counts: { succeeded: 2, idle: 0 } });
    expect(schedulerWorkerNotice(value)).toMatchObject({ tone: 'success', title: 'Job 均报告完成' });
    expect(schedulerWorkerNotice(value)?.detail).toContain('不证明新增内容、下载、导出或可播放');
  });

  it.each([
    null,
    undefined,
    [],
    'DO_NOT_RENDER',
    true,
    {},
    { processed_count: 1 },
    { status_counts: { succeeded: 1 } },
    { processed_count: 1, status_counts: { succeeded: 1 }, secret: 'DO_NOT_RENDER' },
    { processed_count: 1, status_counts: null },
    { processed_count: 1, status_counts: [] },
    { processed_count: 1, status_counts: 'DO_NOT_RENDER' },
    { processed_count: 1, status_counts: { DO_NOT_RENDER: 1 } },
    { processed_count: 1, status_counts: { succeeded: 1, DO_NOT_RENDER: 0 } },
    { processed_count: 2, status_counts: { succeeded: 1 } },
    { processed_count: 0, status_counts: { succeeded: 1 } },
    { processed_count: 1, status_counts: {} },
    { processed_count: '1', status_counts: { succeeded: 1 } },
    { processed_count: true, status_counts: { succeeded: 1 } },
    { processed_count: -1, status_counts: {} },
    { processed_count: 1.5, status_counts: { succeeded: 1.5 } },
    { processed_count: 1, status_counts: { succeeded: '1' } },
    { processed_count: 1, status_counts: { succeeded: true } },
    { processed_count: 1, status_counts: { succeeded: -1, idle: 2 } },
    { processed_count: NaN, status_counts: {} },
    { processed_count: Infinity, status_counts: { succeeded: Infinity } },
    {
      processed_count: Number.MAX_SAFE_INTEGER + 1,
      status_counts: { succeeded: Number.MAX_SAFE_INTEGER + 1 }
    },
    { processed_count: 1001, status_counts: { succeeded: 1001 } },
    JSON.parse('{"processed_count":1,"status_counts":{"__proto__":1}}')
  ])('fails wholly closed for malformed summary %j', (result) => {
    const value = operation(result);
    expect(schedulerWorkerSummary(value)).toBeNull();
    const notice = schedulerWorkerNotice(value);
    expect(notice).toMatchObject({ tone: 'warning', title: '采集结果无法确认' });
    expect(JSON.stringify(notice)).not.toContain('DO_NOT_RENDER');
    expect(JSON.stringify(notice)).not.toContain('__proto__');
  });

  it('accepts the exact backend maximum without borrowing inherited counters', () => {
    const counts = Object.assign(Object.create({ failed_terminal: 1 }), { succeeded: 1000 });
    const value = operation({ processed_count: 1000, status_counts: counts });
    expect(schedulerWorkerSummary(value)).toEqual({
      processed_count: 1000,
      status_counts: { succeeded: 1000 }
    });
  });

  it.each(['queued', 'running', 'cancelled', 'failed_retryable', 'failed_terminal', 'interrupted'] as const)(
    'does not rename or reinterpret scheduler control state %s',
    (state) => {
      const value = operation({ processed_count: 1, status_counts: { succeeded: 1 } }, { state });
      expect(schedulerWorkerStateLabel(value.kind, value.state)).toBeNull();
      expect(schedulerWorkerNotice(value)).toBeNull();
    }
  );

  it.each([
    'account-login',
    'pipeline-run',
    'asset-download',
    'emby-export',
    'media-server-probe',
    'media-server-scan'
  ] as OperationKind[])('does not affect other operation kind %s', (kind) => {
    const value = operation({ processed_count: 1, status_counts: { failed_terminal: 1 } }, { kind });
    expect(schedulerWorkerStateLabel(kind, value.state)).toBeNull();
    expect(schedulerWorkerSummary(value)).toBeNull();
    expect(schedulerWorkerNotice(value)).toBeNull();
  });
});
