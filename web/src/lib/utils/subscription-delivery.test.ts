import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/client';
import type { SubscriptionDeliveryResult } from '$lib/types/api';
import {
  DELIVERY_OBSERVATION_ENDED,
  DELIVERY_UNAVAILABLE,
  EXACT_DELIVERY_NOTICE,
  parseBiliDeliveryProgress,
  parseSubscriptionDeliveryOperation,
  safeBiliDeliveryProgressCard,
  safeScanProgressCards,
  SCAN_PROGRESS_NOTICE,
  subscriptionDeliveryFailure,
  subscriptionDeliveryRequest,
  subscriptionDeliveryResultRows,
  SubscriptionDeliveryController,
  type SubscriptionDeliveryScope
} from './subscription-delivery';

const subscriptionId = '11111111-1111-4111-8111-111111111111';
const operationId = '22222222-2222-4222-8222-222222222222';
const otherId = '33333333-3333-4333-8333-333333333333';
const requestId = '44444444-4444-4444-8444-444444444444';
const accountId = '55555555-5555-4555-8555-555555555555';
const authorId = '66666666-6666-4666-8666-666666666666';
const runId = '77777777-7777-4777-8777-777777777777';
const pipelineId = '88888888-8888-4888-8888-888888888888';
const exportId = '99999999-9999-4999-8999-999999999999';
const sentinel = 'PRIVATE_COOKIE_SIGNED_URL_PATH_DO_NOT_RENDER';

const scope: SubscriptionDeliveryScope = {
  subscription_id: subscriptionId,
  platform: 'bili',
  expected_schedule_revision: 7,
  session_epoch: 2
};

const result: SubscriptionDeliveryResult = {
  subscription_id: subscriptionId,
  account_id: accountId,
  author_id: authorId,
  platform: 'bili',
  sync_job_id: otherId,
  run_id: runId,
  pipeline_job_id: pipelineId,
  export_job_id: exportId,
  discovery_count: 2,
  asset_identity_count: 3,
  updated_count: null,
  discovery_count_semantics: 'created_rows',
  selection_scope: 'author_active_snapshot',
  selected_asset_count: 3,
  verified_asset_count: 3,
  downloaded_count: 2,
  already_verified_count: 1,
  publication_disposition: 'published',
  managed_file_count: 9,
  directory_verified: true
};

const partialResult: SubscriptionDeliveryResult = {
  ...result,
  selection_scope: 'source_run_plus_retry_backlog',
  observed_content_count: 3,
  delivered_content_count: 3,
  failed_content_count: 0,
  retry_backlog_content_count: 2,
  delivered_retry_backlog_content_count: 1,
  failed_retry_backlog_content_count: 1,
  retryable_failed_content_count: 1,
  terminal_failed_content_count: 0,
  failure_codes: ['pipeline_download_retryable'],
  partial: true
};

function operation(
  state: 'running' | 'succeeded' | 'failed_retryable' = 'succeeded',
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: operationId,
    kind: 'subscription-delivery',
    state,
    phase: state === 'succeeded' ? 'directory_verified' : 'delivering_assets',
    progress: state === 'succeeded' ? { current: 3, total: 3, unit: 'steps' } : null,
    target: { type: 'subscription', id: subscriptionId },
    result: state === 'succeeded' ? result : null,
    error_code: state === 'failed_retryable' ? 'subscription_delivery_pipeline_failed' : null,
    ...overrides
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('exact subscription delivery contract', () => {
  it('builds the fixed one-at-a-time request from the freshly read schedule revision', () => {
    expect(
      subscriptionDeliveryRequest(scope, {
        enable_mediacrawler: true,
        accept_mediacrawler_license: true
      })
    ).toEqual({
      expected_schedule_revision: 7,
      global_capacity: 1,
      lease_seconds: 3_600,
      retry_delay_seconds: 30,
      enable_mediacrawler: true,
      accept_mediacrawler_license: true
    });
  });

  it('accepts only the exact subscription target and complete directory evidence', () => {
    expect(parseSubscriptionDeliveryOperation(operation(), scope, operationId)?.result).toEqual(result);
    expect(
      parseSubscriptionDeliveryOperation(
        operation('succeeded', { target: { type: 'subscription', id: otherId } }),
        scope,
        operationId
      )
    ).toBeNull();
    expect(
      parseSubscriptionDeliveryOperation(
        operation('succeeded', { result: { ...result, selected_asset_count: 4 } }),
        scope,
        operationId
      )
    ).toBeNull();
    expect(
      parseSubscriptionDeliveryOperation(
        operation('succeeded', { result: { ...result, selection_scope: 'new_items_only' } }),
        scope,
        operationId
      )
    ).toBeNull();
    expect(
      parseSubscriptionDeliveryOperation(
        operation('succeeded', { result: { ...result, private_path: sentinel } }),
        scope,
        operationId
      )
    ).toBeNull();
  });

  it('projects only fixed result copy and explains author_active_snapshot honestly', () => {
    const rows = subscriptionDeliveryResultRows(result);
    const text = JSON.stringify(rows);
    expect(text).toContain('作者当前有效资产快照');
    expect(text).toContain('已全部验证');
    expect(text).toContain('不依赖媒体服务器连接');
    expect(EXACT_DELIVERY_NOTICE).toContain('author_active_snapshot');
    expect(EXACT_DELIVERY_NOTICE).toContain('不是“仅本轮新增”');
    expect(EXACT_DELIVERY_NOTICE).toContain('采集→下载→归档→生成兼容目录');
    expect(EXACT_DELIVERY_NOTICE).toContain('不要求连接 Emby 或 Jellyfin');
  });

  it('accepts a closed partial content receipt and rejects inconsistent failure evidence', () => {
    const parsed = parseSubscriptionDeliveryOperation(
      operation('succeeded', { result: partialResult }),
      scope,
      operationId
    );
    expect(parsed?.result).toEqual(partialResult);
    expect(JSON.stringify(subscriptionDeliveryResultRows(partialResult))).toContain('重试积压内容');
    expect(
      parseSubscriptionDeliveryOperation(
        operation('succeeded', {
          result: { ...partialResult, delivered_content_count: 2 }
        }),
        scope,
        operationId
      )
    ).toBeNull();
    expect(
      parseSubscriptionDeliveryOperation(
        operation('succeeded', {
          result: { ...partialResult, failure_codes: ['pipeline_download_retryable', sentinel] }
        }),
        scope,
        operationId
      )
    ).toBeNull();
  });
});

describe('one delivery observation lifetime', () => {
  it('tracks the returned exact Operation through phases to verified success', async () => {
    const read = vi
      .fn<(_operationId: string, _signal: AbortSignal) => Promise<unknown>>()
      .mockResolvedValueOnce(operation('running'))
      .mockResolvedValueOnce(operation('succeeded'));
    const start = vi.fn(async (_scope: SubscriptionDeliveryScope, _key: string, _signal: AbortSignal) => ({
      operation_id: operationId,
      state: 'queued'
    }));
    const published = vi.fn();
    const controller = new SubscriptionDeliveryController(
      { licenseConfirmed: () => true, start, read },
      published,
      () => requestId,
      async () => undefined
    );
    controller.setScope(scope);
    await controller.start();

    expect(start).toHaveBeenCalledOnce();
    expect(start.mock.calls[0][0]).toEqual(scope);
    expect(start.mock.calls[0][1]).toBe(requestId);
    expect(read).toHaveBeenCalledTimes(2);
    expect(controller.snapshot.phase).toBe('succeeded');
    expect(controller.snapshot.operation_id).toBe(operationId);
    expect(controller.snapshot.operation?.result).toEqual(result);
    expect(published.mock.calls.some(([view]) => view.operation?.phase === 'delivering_assets')).toBe(true);
    controller.dispose();
  });

  it('aborts an old response generation and never applies it to another subscription', async () => {
    const pending = deferred<unknown>();
    let oldSignal!: AbortSignal;
    const controller = new SubscriptionDeliveryController(
      {
        licenseConfirmed: () => true,
        start: async (_scope, _key, signal) => {
          oldSignal = signal;
          return { operation_id: operationId, state: 'queued' };
        },
        read: async () => pending.promise
      },
      vi.fn(),
      () => requestId
    );
    controller.setScope(scope);
    const old = controller.start();
    await Promise.resolve();
    await Promise.resolve();
    controller.setScope({ ...scope, subscription_id: otherId });
    expect(oldSignal.aborted).toBe(true);
    pending.resolve(operation());
    await old;
    expect(controller.snapshot.scope?.subscription_id).toBe(otherId);
    expect(controller.snapshot.operation_id).toBeNull();
    expect(controller.snapshot.phase).toBe('idle');
    controller.dispose();
  });

  it('retains the exact Operation ID when local observation fails and does not invent server rollback', async () => {
    const controller = new SubscriptionDeliveryController(
      {
        licenseConfirmed: () => true,
        start: async () => ({ operation_id: operationId, state: 'queued' }),
        read: async () => {
          throw new ApiError(500, sentinel, sentinel);
        }
      },
      vi.fn(),
      () => requestId
    );
    controller.setScope(scope);
    await controller.start();
    expect(controller.snapshot.phase).toBe('wait_ended');
    expect(controller.snapshot.operation_id).toBe(operationId);
    expect(controller.snapshot.message).toBe(DELIVERY_OBSERVATION_ENDED);
    expect(controller.snapshot.message).not.toContain(sentinel);
    controller.dispose();
  });

  it('fails closed before an Operation ID and never reflects unknown server detail', async () => {
    const controller = new SubscriptionDeliveryController(
      {
        licenseConfirmed: () => true,
        start: async () => {
          throw new ApiError(500, sentinel, { detail: sentinel });
        },
        read: vi.fn()
      },
      vi.fn(),
      () => requestId
    );
    controller.setScope(scope);
    await controller.start();
    expect(controller.snapshot.phase).toBe('failed');
    expect(controller.snapshot.operation_id).toBeNull();
    expect(controller.snapshot.message).toBe(DELIVERY_UNAVAILABLE);
    expect(subscriptionDeliveryFailure(new ApiError(409, 'operation_already_running', null))).toContain(
      '没有重复提交'
    );
    expect(
      subscriptionDeliveryFailure(new ApiError(400, 'subscription_delivery_mediacrawler_not_enabled', null))
    ).toContain('没有创建采集或下载任务');
    expect(
      subscriptionDeliveryFailure(new ApiError(400, 'subscription_delivery_license_required', null))
    ).toContain('没有创建采集或下载任务');
    expect(subscriptionDeliveryFailure('subscription_delivery_cancel_unsupported')).toContain(
      '不会虚假声称取消'
    );
    expect(subscriptionDeliveryFailure('__proto__')).toBe(DELIVERY_UNAVAILABLE);
    controller.dispose();
  });
});

describe('durable scan progress display', () => {
  it('shows committed counters while source_end_observed remains explicitly incomplete', () => {
    const cards = safeScanProgressCards({
      schema_version: 1,
      history_complete: false,
      feeds: [
        {
          feed: 'uploads',
          state: 'source_end_observed',
          unit_count: 3,
          item_count: 61,
          history_unit_count: 2,
          history_item_count: 31,
          last_lane: 'history',
          last_stop_reason: 'source_end',
          contract_version: 1,
          upstream_sha: 'a'.repeat(40),
          generation_id: otherId,
          checkpoint_revision: 3,
          source_end_run_id: runId,
          private_cursor: sentinel
        }
      ]
    });
    const text = JSON.stringify(cards);
    expect(text).toContain('曾观察到当前来源末尾');
    expect(text).toContain('不等于历史完整');
    expect(text).toContain('2 轮 / 31 条');
    expect(text).not.toContain(sentinel);
    expect(SCAN_PROGRESS_NOTICE).toContain('都不声明全历史完成');
  });

  it('keeps all six non-Bili placeholder feeds unproven and fails closed on malformed truth claims', () => {
    for (const feed of ['notes', 'posts', 'threads', 'answers']) {
      const cards = safeScanProgressCards({
        schema_version: 1,
        history_complete: false,
        feeds: [
          {
            feed,
            state: 'unproven',
            unit_count: 0,
            item_count: 0,
            history_unit_count: 0,
            history_item_count: 0,
            last_lane: null,
            last_stop_reason: null
          }
        ]
      });
      expect(cards[0].state).toContain('未证明');
    }
    expect(
      safeScanProgressCards({
        schema_version: 1,
        history_complete: true,
        feeds: []
      })[0].state
    ).toContain('不声明全历史完成');
  });
});

describe('delivery-qualified Bili baseline display', () => {
  const progress = {
    schema_version: 1,
    initialized: true,
    phase: 'incremental',
    baseline_snapshot_complete: true,
    generation_id: otherId,
    batch_count: 4,
    content_observation_count: 67,
    backfill_batch_count: 3,
    reconciliation_batch_count: 1,
    incremental_batch_count: 0,
    partial_batch_count: 1,
    failed_content_count: 1,
    last_lane: 'head',
    last_stop_reason: 'head_boundary',
    last_delivery_at: '2026-09-07T12:00:00+00:00',
    source_end_observed_at: '2026-09-07T11:00:00+00:00',
    source_end_run_id: runId,
    reconciled_at: '2026-09-07T12:00:00+00:00',
    reconciliation_run_id: requestId,
    baseline_snapshot_at: '2026-09-07T12:00:00+00:00',
    next_eligible_at: '2026-09-07T18:00:00+00:00',
    blocked_code: null
  };

  it('strictly parses bounded counters and labels a reconciled snapshot as incremental', () => {
    expect(parseBiliDeliveryProgress(progress)?.phase).toBe('incremental');
    const card = safeBiliDeliveryProgressCard(progress);
    expect(card.phase).toBe('增量检查');
    expect(JSON.stringify(card.rows)).toContain('67 条');
    expect(card.notice).toContain('不表示平台历史永久完整');
  });

  it('fails closed without reflecting unknown fields or inconsistent completion claims', () => {
    for (const value of [
      { ...progress, private_cursor: sentinel },
      { ...progress, baseline_snapshot_complete: false },
      { ...progress, incremental_batch_count: 1 },
      { ...progress, source_end_run_id: null },
      {
        ...progress,
        initialized: false,
        phase: 'reconciling',
        baseline_snapshot_complete: false,
        generation_id: null,
        batch_count: 0,
        content_observation_count: 0,
        backfill_batch_count: 0,
        reconciliation_batch_count: 0,
        partial_batch_count: 0,
        failed_content_count: 0,
        last_lane: null,
        last_stop_reason: null,
        last_delivery_at: null,
        source_end_observed_at: null,
        source_end_run_id: null,
        reconciled_at: null,
        reconciliation_run_id: null,
        baseline_snapshot_at: null,
        blocked_code: null
      }
    ]) {
      expect(parseBiliDeliveryProgress(value)).toBeNull();
      expect(JSON.stringify(safeBiliDeliveryProgressCard(value))).not.toContain(sentinel);
    }
  });
});

describe('subscriptions route wiring', () => {
  it('separates schedule advancement from exact collection and exposes durable evidence links', () => {
    const source = readFileSync(new URL('../../routes/subscriptions/+page.svelte', import.meta.url), 'utf8');
    expect(source).toContain('仅推进调度');
    expect(source).toContain('采集→下载→归档→生成兼容目录');
    expect(source).toContain('/execute`');
    expect(source).toContain('expected_schedule_revision');
    expect(source).toContain('mediaCrawlerGate()');
    expect(source).toContain('/logs?operation_id=');
    expect(source).toContain('safeScanProgressCards');
    expect(source).toContain('safeBiliDeliveryProgressCard');
    expect(source).not.toContain('已安排同步任务；完成状态请到任务页面核对。');
  });
});
