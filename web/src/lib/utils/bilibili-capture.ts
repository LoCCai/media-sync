import type { PlatformCapability } from '$lib/types/api';

type Row = { label: string; value: string };
const LANES: Record<string, string> = { head: '头部更新', history: '历史回填' };
const REASONS: Record<string, string> = {
  item_limit: '达到本单元条目上限',
  list_limit: '达到作者列表请求预算',
  restarted: '分页见证变化，已保守重启',
  source_end: '本次通道观察到源末尾',
  head_boundary: '本次头部扫描观察到旧边界'
};

export function isBiliBoundedCapture(capability: PlatformCapability | null): boolean {
  const budget = capability?.bounded_capture;
  return Boolean(
    capability?.platform === 'bili' &&
      capability.requires_full_history_acknowledgement === false &&
      budget?.version === 1 &&
      budget.feed === 'ordinary_uploads' &&
      budget.order === 'pubdate' &&
      budget.page_size === 30 &&
      budget.max_items_per_unit === 30 &&
      budget.max_list_attempts_per_unit === 2 &&
      Array.isArray(budget.alternating_lanes) &&
      budget.alternating_lanes.length === 2 &&
      budget.alternating_lanes[0] === 'head' &&
      budget.alternating_lanes[1] === 'history' &&
      budget.browser_setup_separate === true &&
      budget.download_scope_bounded === false &&
      budget.history_completeness_claimed === false &&
      budget.legacy_requires_full_history_acknowledgement === true
  );
}

export function biliUnitItemLimit(maxItems: number): number {
  return Number.isFinite(maxItems) && maxItems >= 1 ? Math.min(Math.trunc(maxItems), 30) : 30;
}

export function biliCaptureNotice(maxItems: number, scope: string = 'uploads'): string {
  if (scope === 'dynamics' || scope === 'both') {
    return `B站每单元最多 ${biliUnitItemLimit(maxItems)} 条入库记录；动态视频引用预留动态和投稿两条，因此单次上限至少为 2。每次只推进一个来源，发现页可仅保存待处理断点而不新增内容；下一轮继续精确详情。支持自有文字、静态图集和普通视频引用，不递归转发、不采集评论。部分推进不等于历史完整。下载范围另计；本地目录输出不需要连接 Emby/Jellyfin。`;
  }
  return `B站每个采集单元最多验证 ${biliUnitItemLimit(maxItems)} 条普通投稿详情（min(max_items, 30)），作者列表最多尝试 2 次，失败也计数。头部更新与历史回填交替推进；部分推进或观察到源末尾不等于全历史完成。浏览器与认证初始化另有运行时预算，签名密钥最多另读 2 次。该上限不限制下载范围，下载队列仍可能处理此订阅此前待办资产；动态、粉丝、关注、评论不在本次采集范围。`;
}

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function count(value: unknown, maximum: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= maximum;
}

function code(value: unknown, vocabulary: Record<string, string>): value is string {
  return typeof value === 'string' && Object.hasOwn(vocabulary, value);
}

export function safeBiliScanSummaryRows(value: unknown): Row[] {
  const unavailable = [{ label: 'B站覆盖证据', value: '不可用；未声明历史完整，也不从旧水位推断覆盖。' }];
  if (record(value) && value.version === 2) {
    const scopes: Record<string, string> = { uploads: '仅投稿', dynamics: '仅动态', both: '投稿与动态' };
    const state = value.state;
    if (
      !code(value.feed, scopes) ||
      !count(value.unit_item_limit, 30) ||
      value.unit_item_limit < 1 ||
      value.history_complete !== false
    )
      return unavailable;
    if (value.status === 'not_started' && state === null) {
      return [
        { label: '计划采集范围', value: scopes[value.feed] },
        { label: 'B站检查点', value: '尚未采集；首次动态单元仅保存私密发现页，后续验证详情' },
        { label: '覆盖结论', value: '尚无采集证据，不声明全历史完成' }
      ];
    }
    if (
      value.status !== 'verified' ||
      !record(state) ||
      state.version !== 2 ||
      !code(state.scope, scopes) ||
      !['uploads', 'dynamics'].includes(String(state.next_feed))
    )
      return unavailable;
    const uploads = state.uploads;
    const dynamics = state.dynamics;
    if (
      !record(uploads) ||
      !record(dynamics) ||
      !count(uploads.pending_count, 60) ||
      !count(dynamics.pending_count, 60) ||
      !code(dynamics.next_lane, LANES) ||
      !code(uploads.next_lane, LANES)
    )
      return unavailable;
    return [
      { label: '检查点采集范围', value: `${scopes[state.scope]}；修改策略后以新策略为准，下次运行保留断点` },
      { label: '下一来源', value: state.next_feed === 'uploads' ? '普通投稿' : '动态' },
      {
        label: '投稿进展',
        value: `待处理 ${uploads.pending_count} 项，下一通道：${LANES[uploads.next_lane]}`
      },
      {
        label: '动态进展',
        value: `私密页中待处理 ${dynamics.pending_count} 项，下一通道：${LANES[dynamics.next_lane]}`
      },
      { label: '每单元入库上限', value: `${value.unit_item_limit} 条；动态视频引用预留两条，下载另计` },
      { label: '覆盖结论', value: '部分推进；发现页可能仅保存待处理快照，不代表全历史完整' }
    ];
  }
  if (
    !record(value) ||
    value.version !== 1 ||
    value.feed !== 'ordinary_uploads' ||
    !count(value.unit_item_limit, 30) ||
    value.unit_item_limit < 1 ||
    value.max_list_attempts !== 2 ||
    value.history_complete !== false ||
    !['not_started', 'unverified', 'verified'].includes(String(value.status))
  )
    return unavailable;
  const rows = [
    { label: '每单元详情上限', value: `${value.unit_item_limit} 条普通投稿；不是下载上限` },
    { label: '作者列表预算', value: '最多 2 次 HTTP 尝试；浏览器、认证与最多 2 次签名密钥读取另计' },
    { label: '覆盖结论', value: '尚无可验证的新格式单元推进证据；不声明全历史完成' }
  ];
  if (value.status !== 'verified') {
    return [
      ...rows,
      {
        label: 'B站检查点',
        value:
          value.status === 'not_started'
            ? '尚无新格式扫描证据；下一次受控运行从头部开始'
            : '旧格式或无法校验；不授予有界/完整覆盖结论，需从新格式受控扫描建立证据'
      }
    ];
  }
  const state = value.state;
  if (
    !record(state) ||
    state.version !== 1 ||
    !code(state.next_lane, LANES) ||
    typeof state.head_boundary_established !== 'boolean' ||
    typeof state.history_active !== 'boolean' ||
    !count(state.pending_count, 60)
  )
    return unavailable;
  const last = state.last_unit;
  if (
    last !== null &&
    (!record(last) ||
      !code(last.lane, LANES) ||
      !code(last.stop_reason, REASONS) ||
      !count(last.item_count, 30) ||
      !count(last.list_attempts, 2) ||
      !count(last.detail_attempts, 30))
  )
    return unavailable;
  rows.push(
    { label: '下一步', value: `下一次受控运行继续${LANES[state.next_lane]}` },
    {
      label: '回填活动',
      value: state.history_active ? '已配置交替回填，末尾后可在后续轮次重新巡检' : '未活动'
    },
    { label: '头部边界', value: state.head_boundary_established ? '已建立，仅限已消费边界' : '尚未建立' },
    { label: '待消费身份', value: `保留 ${state.pending_count} 项；不显示原始标识` }
  );
  if (record(last)) {
    rows[2].value = '部分推进（partial），不声明全历史完成';
    rows.push(
      { label: '最近单元通道', value: LANES[last.lane as string] },
      { label: '最近停止原因', value: REASONS[last.stop_reason as string] },
      { label: '最近已验证条目', value: `${last.item_count} 条` },
      {
        label: '分页重启',
        value: last.stop_reason === 'restarted' ? '已保守重启，不提升覆盖结论' : '本单元未重启'
      },
      {
        label: '源末尾观察',
        value: last.stop_reason === 'source_end' ? '仅本次通道观察，不代表全历史完整' : '本单元未观察到'
      }
    );
  }
  return rows;
}
