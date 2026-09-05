import { describe, expect, it } from 'vitest';
import type { PlatformCapability } from '$lib/types/api';
import {
  biliCaptureNotice,
  biliUnitItemLimit,
  isBiliBoundedCapture,
  safeBiliScanSummaryRows
} from './bilibili-capture';

const capability = {
  platform: 'bili',
  requires_full_history_acknowledgement: false,
  bounded_capture: {
    version: 1,
    feed: 'ordinary_uploads',
    order: 'pubdate',
    page_size: 30,
    max_items_per_unit: 30,
    max_list_attempts_per_unit: 2,
    alternating_lanes: ['head', 'history'],
    browser_setup_separate: true,
    download_scope_bounded: false,
    history_completeness_claimed: false,
    legacy_requires_full_history_acknowledgement: true
  }
} as PlatformCapability;

const state = {
  version: 1,
  next_lane: 'history',
  head_boundary_established: false,
  pending_count: 29,
  history_active: true,
  last_unit: { lane: 'head', stop_reason: 'item_limit', item_count: 1, list_attempts: 1, detail_attempts: 1 }
};
const summary = {
  version: 1,
  status: 'verified',
  feed: 'ordinary_uploads',
  unit_item_limit: 1,
  max_list_attempts: 2,
  history_complete: false,
  state
};

describe('Bili per-unit limits', () => {
  it('shows the effective min and discloses separate runtime, uploads-only and download scope', () => {
    expect(biliUnitItemLimit(1)).toBe(1);
    expect(biliUnitItemLimit(1000)).toBe(30);
    expect(biliUnitItemLimit(NaN)).toBe(30);
    const notice = biliCaptureNotice(1);
    for (const expected of [
      '1 条普通投稿详情',
      '最多尝试 2 次',
      '失败也计数',
      '浏览器与认证',
      '不限制下载范围',
      '不等于全历史完成',
      '动态、粉丝、关注、评论'
    ]) {
      expect(notice).toContain(expected);
    }
  });

  it('never grants new semantics to an old or foreign capability', () => {
    expect(isBiliBoundedCapture(capability)).toBe(true);
    expect(isBiliBoundedCapture(null)).toBe(false);
    expect(isBiliBoundedCapture({ ...capability, bounded_capture: undefined })).toBe(false);
    expect(isBiliBoundedCapture({ ...capability, platform: 'wb' })).toBe(false);
    expect(isBiliBoundedCapture({ ...capability, requires_full_history_acknowledgement: true })).toBe(false);
    expect(
      isBiliBoundedCapture({
        ...capability,
        bounded_capture: { ...capability.bounded_capture, alternating_lanes: ['head'] }
      } as never)
    ).toBe(false);
    expect(
      isBiliBoundedCapture({
        ...capability,
        bounded_capture: { ...capability.bounded_capture, version: 2 }
      } as never)
    ).toBe(false);
  });
});

describe('safe Bili coverage projection', () => {
  it('renders partial lane progress without raw cursors, IDs, paths or unknown fields', () => {
    const rows = safeBiliScanSummaryRows({
      ...summary,
      raw_cursor: 'COOKIE_PRIVATE',
      state: {
        ...state,
        pending: ['PRIVATE_BVID'],
        witness: 'C:\\private\\profile',
        signed_url: 'PRIVATE_URL'
      }
    });
    const text = JSON.stringify(rows);
    expect(text).toContain('部分推进（partial）');
    expect(text).toContain('继续历史回填');
    expect(text).toContain('保留 29 项');
    for (const forbidden of ['COOKIE_PRIVATE', 'PRIVATE_BVID', 'PRIVATE_URL', 'profile', 'raw_cursor'])
      expect(text).not.toContain(forbidden);
  });

  it.each(['source_end', 'restarted', 'head_boundary', 'list_limit'])(
    'explains %s without claiming completeness',
    (reason) => {
      const text = JSON.stringify(
        safeBiliScanSummaryRows({
          ...summary,
          state: {
            ...state,
            last_unit: { ...state.last_unit, stop_reason: reason }
          }
        })
      );
      expect(text).toContain('不声明全历史完成');
      if (reason === 'source_end') expect(text).toContain('仅本次通道观察');
      if (reason === 'restarted') expect(text).toContain('已保守重启，不提升覆盖结论');
    }
  );

  it.each(['not_started', 'unverified'])('keeps %s distinct from verified coverage', (status) => {
    const text = JSON.stringify(safeBiliScanSummaryRows({ ...summary, status, state: null }));
    expect(text).not.toContain('最近已验证条目');
    expect(text).not.toContain('部分推进（partial）');
    expect(text).toContain(status === 'not_started' ? '尚无新格式扫描证据' : '旧格式或无法校验');
  });

  it.each([
    null,
    { ...summary, version: 2 },
    { ...summary, history_complete: true },
    { ...summary, unit_item_limit: 31 },
    { ...summary, max_list_attempts: 3 },
    { ...summary, state: { ...state, next_lane: 'PRIVATE' } },
    { ...summary, state: { ...state, pending_count: 61 } },
    { ...summary, state: { ...state, last_unit: { ...state.last_unit, stop_reason: 'PRIVATE' } } },
    { ...summary, state: { ...state, last_unit: { ...state.last_unit, list_attempts: 3 } } },
    { ...summary, state: { ...state, last_unit: { ...state.last_unit, item_count: 31 } } }
  ])('fails closed on invalid summary %j', (value) => {
    expect(safeBiliScanSummaryRows(value)).toEqual([
      { label: 'B站覆盖证据', value: '不可用；未声明历史完整，也不从旧水位推断覆盖。' }
    ]);
  });
});
