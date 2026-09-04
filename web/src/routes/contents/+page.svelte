<script lang="ts">
  import { afterNavigate } from '$app/navigation';
  import { onDestroy } from 'svelte';
  import {
    Archive,
    Download,
    ExternalLink,
    Eye,
    FileText,
    Image,
    RefreshCw,
    Search,
    Video,
    X
  } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { mediaCrawlerGate } from '$lib/stores/onboarding';
  import { toast } from '$lib/stores/toast';
  import type { Asset, ContentDetail, ContentItem, ContentKind, Platform } from '$lib/types/api';
  import {
    assetActions,
    assetArchiveUrl,
    assetRecoveryAvailable,
    assetRecoveryUrl,
    buildExplorerQuery,
    contentExplorerQueryState,
    EXPLORER_RESULT_LIMIT
  } from '$lib/utils/explorer';
  import { formatBytes, formatDate, formatDateLong, PLATFORM_META, shortId } from '$lib/utils/format';

  let contents: ContentItem[] = [];
  let loading = true;
  let error = '';
  let search = '';
  let platform: Platform | 'all' = 'all';
  let kind: ContentKind | 'all' = 'all';
  let archived: boolean | 'all' = 'all';
  let exported: boolean | 'all' = 'all';
  let authorId = '';
  let mounted = false;
  let listRequest = 0;
  let searchTimer: number | undefined;

  let detailOpen = false;
  let detailLoading = false;
  let detailError = '';
  let detail: ContentDetail | null = null;
  let selectedSummary: ContentItem | null = null;
  let detailRequest = 0;
  let previewAssetId = '';
  let previewFailures: Record<string, boolean> = {};
  let acting = '';

  $: complete = contents.filter((item) => item.archive_state === 'complete').length;
  $: exportedCount = contents.filter((item) => item.export_count > 0).length;
  $: hasFilters =
    Boolean(search.trim() || authorId) ||
    platform !== 'all' ||
    kind !== 'all' ||
    archived !== 'all' ||
    exported !== 'all';

  async function load(): Promise<void> {
    if (!mounted) return;
    if (searchTimer !== undefined) window.clearTimeout(searchTimer);
    const request = ++listRequest;
    loading = true;
    error = '';
    try {
      const result = await api<ContentItem[]>(
        buildExplorerQuery('/api/v1/contents', {
          q: search,
          platform,
          kind,
          author_id: authorId,
          archived,
          exported,
          limit: EXPLORER_RESULT_LIMIT
        })
      );
      if (request === listRequest) contents = result;
    } catch (caught) {
      if (request === listRequest) error = apiMessage(caught);
    } finally {
      if (request === listRequest) loading = false;
    }
  }

  function scheduleLoad(): void {
    if (!mounted) return;
    if (searchTimer !== undefined) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => void load(), 280);
  }

  function clearAuthor(): void {
    authorId = '';
    const next = new URL(window.location.href);
    next.searchParams.delete('author_id');
    window.history.replaceState({}, '', `${next.pathname}${next.search}${next.hash}`);
    void load();
  }

  async function openDetail(item: ContentItem): Promise<void> {
    const request = ++detailRequest;
    selectedSummary = item;
    detail = null;
    detailError = '';
    detailLoading = true;
    detailOpen = true;
    previewAssetId = '';
    previewFailures = {};
    try {
      const result = await api<ContentDetail>(`/api/v1/contents/${encodeURIComponent(item.id)}`);
      if (request === detailRequest) detail = result;
    } catch (caught) {
      if (request === detailRequest) detailError = apiMessage(caught);
    } finally {
      if (request === detailRequest) detailLoading = false;
    }
  }

  function togglePreview(assetId: string): void {
    previewAssetId = previewAssetId === assetId ? '' : assetId;
    previewFailures = { ...previewFailures, [assetId]: false };
  }

  function markPreviewFailed(assetId: string): void {
    previewFailures = { ...previewFailures, [assetId]: true };
  }

  async function downloadAsset(asset: Asset): Promise<void> {
    if (!assetRecoveryAvailable(assetActions(asset))) return;
    acting = asset.id;
    try {
      const started = await api<{ operation_id: string }>(assetRecoveryUrl(asset.id), {
        method: 'POST',
        body: JSON.stringify({ ...mediaCrawlerGate() })
      });
      toast(`资产恢复已启动 · ${shortId(started.operation_id)}`);
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      acting = '';
    }
  }

  function kindIcon(itemKind: ContentKind): typeof Video {
    if (['video', 'dynamic', 'mixed'].includes(itemKind)) return Video;
    if (['image', 'gallery'].includes(itemKind)) return Image;
    return FileText;
  }

  function archiveLabel(item: ContentItem): string {
    return (
      {
        empty: '无媒体',
        pending: '待归档',
        partial: '部分归档',
        complete: '完整归档'
      }[item.archive_state] ?? item.archive_state
    );
  }

  afterNavigate(() => {
    const query = contentExplorerQueryState(new URLSearchParams(window.location.search));
    search = query.q;
    platform = query.platform;
    kind = query.kind;
    authorId = query.author_id;
    archived = query.archived;
    exported = query.exported;
    mounted = true;
    void load();
  });

  onDestroy(() => {
    listRequest += 1;
    detailRequest += 1;
    if (searchTimer !== undefined) window.clearTimeout(searchTimer);
  });
</script>

<div class="page">
  <PageHeader title="内容" description="按服务端目录查找内容，查看完整正文、归档资产与导出事实。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={load} disabled={loading}>
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新
      </button>
    </svelte:fragment>
  </PageHeader>

  <section class="summary-grid content-summary">
    <div class="summary-item">
      <span class="summary-label">当前结果<FileText size={16} /></span>
      <strong class="summary-value">{contents.length}</strong>
      <span class="summary-hint">最多返回 {EXPLORER_RESULT_LIMIT} 条</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">含媒体<Video size={16} /></span>
      <strong class="summary-value">{contents.filter((item) => item.asset_count > 0).length}</strong>
      <span class="summary-hint">至少发现 1 个资产</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">完整归档<Archive size={16} /></span>
      <strong class="summary-value">{complete}</strong>
      <span class="summary-hint">全部资产处于已校验 / 已导出状态</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">已有导出<FileText size={16} /></span>
      <strong class="summary-value">{exportedCount}</strong>
      <span class="summary-hint">存在成功导出记录</span>
    </div>
  </section>

  <Panel title="内容目录" description={`${contents.length} 条服务端结果`} flush>
    <svelte:fragment slot="actions">
      <div class="filters compact-filters">
        <div class="search-field">
          <Search size={14} />
          <input
            bind:value={search}
            on:input={scheduleLoad}
            aria-label="搜索内容"
            placeholder="标题、作者或 ID"
          />
        </div>
        <select class="select filter-select" bind:value={platform} on:change={load} aria-label="平台筛选">
          <option value="all">全部平台</option>
          {#each Object.entries(PLATFORM_META) as [value, meta]}
            <option {value}>{meta.name}</option>
          {/each}
        </select>
        <select class="select filter-select" bind:value={kind} on:change={load} aria-label="类型筛选">
          <option value="all">全部类型</option>
          <option value="video">视频</option>
          <option value="gallery">图集</option>
          <option value="image">图片</option>
          <option value="audio">音频</option>
          <option value="text">文本</option>
          <option value="article">文章</option>
          <option value="dynamic">动态</option>
          <option value="mixed">混合</option>
        </select>
        <select class="select filter-select" bind:value={archived} on:change={load} aria-label="归档筛选">
          <option value="all">全部归档</option>
          <option value={true}>已完整归档</option>
          <option value={false}>未完整归档</option>
        </select>
        <select class="select filter-select" bind:value={exported} on:change={load} aria-label="导出筛选">
          <option value="all">全部导出</option>
          <option value={true}>已有导出</option>
          <option value={false}>尚未导出</option>
        </select>
      </div>
    </svelte:fragment>

    {#if authorId}
      <div class="active-scope">
        <span>正在查看作者 <span class="mono">{shortId(authorId)}</span> 的内容</span>
        <button class="button ghost small" type="button" on:click={clearAuthor}
          ><X size={14} />清除下钻</button
        >
      </div>
    {/if}

    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(5) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if contents.length === 0}
      <EmptyState
        title={hasFilters ? '没有匹配内容' : '还没有入库内容'}
        description={hasFilters ? '调整搜索或筛选条件后再试。' : '完成一次订阅同步后，内容会出现在这里。'}
      >
        {#if !hasFilters}<a class="button secondary small" href="/jobs">前往任务队列</a>{/if}
      </EmptyState>
    {:else}
      <div class="table-wrap">
        <table class="data-table content-table">
          <thead>
            <tr><th>内容</th><th>平台 / 作者</th><th>发布时间</th><th>资产</th><th>归档</th><th>来源</th></tr>
          </thead>
          <tbody>
            {#each contents as item}
              {@const KindIcon = kindIcon(item.kind)}
              <tr>
                <td>
                  <div class="content-identity">
                    <span class="kind-icon"><KindIcon size={16} /></span>
                    <div>
                      <button
                        class="detail-link content-title"
                        type="button"
                        on:click={() => openDetail(item)}
                      >
                        {item.title || item.body_excerpt || `${item.kind} · ${shortId(item.remote_id)}`}
                      </button>
                      <span class="cell-sub">{item.kind} · {shortId(item.id)}</span>
                    </div>
                  </div>
                </td>
                <td>
                  <div class="inline-identity">
                    <PlatformMark platform={item.platform} />
                    <div>
                      <a
                        class="cell-main author-link"
                        href={`/contents?author_id=${encodeURIComponent(item.author_id)}`}
                      >
                        {item.author_display_name}
                      </a>
                      <span class="cell-sub">{PLATFORM_META[item.platform].name}</span>
                    </div>
                  </div>
                </td>
                <td>{formatDate(item.published_at)}</td>
                <td>
                  <span class="cell-main">{item.archived_count} / {item.asset_count}</span>
                  <span class="cell-sub">已归档 / 全部</span>
                </td>
                <td>
                  <StatusBadge
                    status={item.archive_state === 'complete'
                      ? 'verified'
                      : item.archive_state === 'partial'
                        ? 'downloading'
                        : item.archive_state === 'pending'
                          ? 'queued'
                          : 'discovered'}
                    label={archiveLabel(item)}
                  />
                </td>
                <td>
                  {#if item.canonical_url}
                    <a
                      class="source-link"
                      href={item.canonical_url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label="打开原始内容"><ExternalLink size={15} /></a
                    >
                  {:else}—{/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </Panel>
</div>

<Modal
  bind:open={detailOpen}
  title={selectedSummary?.title || '内容详情'}
  description={selectedSummary
    ? `${PLATFORM_META[selectedSummary.platform].name} · ${selectedSummary.author_display_name}`
    : null}
  wide
>
  {#if detailLoading}
    <div class="detail-loading">
      {#each Array(4) as _}<div class="skeleton"></div>{/each}
    </div>
  {:else if detailError}
    <div class="notice danger">{detailError}</div>
  {:else if detail}
    <div class="detail-stack">
      <section>
        <div class="section-heading">
          <h3>正文</h3>
          {#if detail.tombstoned}<StatusBadge status="failed" label="来源已移除" />{/if}
        </div>
        <p class="body-text">{detail.body || '这条内容没有正文。'}</p>
      </section>

      <dl class="key-value-list detail-facts">
        <div class="key-value-row">
          <dt>发布时间</dt>
          <dd>{formatDateLong(detail.published_at)}</dd>
        </div>
        <div class="key-value-row">
          <dt>远端更新时间</dt>
          <dd>{formatDateLong(detail.remote_updated_at)}</dd>
        </div>
        <div class="key-value-row">
          <dt>首次入库</dt>
          <dd>{formatDateLong(detail.first_seen_at)}</dd>
        </div>
        <div class="key-value-row">
          <dt>最近发现</dt>
          <dd>{formatDateLong(detail.last_seen_at)}</dd>
        </div>
        <div class="key-value-row">
          <dt>成功导出</dt>
          <dd>
            {detail.exports.succeeded_count} 次 · 最近 {formatDateLong(detail.exports.last_exported_at)}
          </dd>
        </div>
      </dl>

      <section>
        <div class="section-heading">
          <h3>关联资产</h3>
          <span>{detail.assets.length} 个，按内容顺序排列</span>
        </div>
        {#if detail.assets.length === 0}
          <div class="detail-empty">这条内容没有媒体资产。</div>
        {:else}
          <div class="asset-list">
            {#each detail.assets as asset}
              {@const actions = assetActions(asset)}
              <article class="asset-card">
                <div class="asset-card-main">
                  <div>
                    <strong>{asset.kind} #{asset.position + 1}</strong>
                    <span>{asset.mime_type ?? '未知媒体类型'} · {formatBytes(asset.size_bytes)}</span>
                  </div>
                  <StatusBadge status={asset.status} />
                </div>
                <div class="asset-card-actions">
                  <a class="button ghost small" href={`/assets?q=${encodeURIComponent(asset.id)}`}>
                    <Eye size={14} />资产详情
                  </a>
                  {#if actions.canPreview && actions.previewKind !== 'new-tab'}
                    <button
                      class="button secondary small"
                      type="button"
                      on:click={() => togglePreview(asset.id)}
                    >
                      <Eye size={14} />{previewAssetId === asset.id ? '收起预览' : '预览'}
                    </button>
                  {/if}
                  {#if actions.canPreview}
                    <a
                      class="button ghost small"
                      href={assetArchiveUrl(asset.id)}
                      target="_blank"
                      rel="noreferrer"><ExternalLink size={14} />新标签</a
                    >
                  {/if}
                  {#if assetRecoveryAvailable(actions)}
                    <button
                      class="button secondary small"
                      type="button"
                      on:click={() => downloadAsset(asset)}
                      disabled={!!acting}
                      ><Download size={14} />{acting === asset.id ? '启动中…' : '下载 / 恢复'}</button
                    >
                  {/if}
                </div>

                {#if previewAssetId === asset.id && actions.canPreview}
                  <div class="preview-frame">
                    {#if previewFailures[asset.id]}
                      <div class="notice warning">
                        归档预览不可用。{assetRecoveryAvailable(actions)
                          ? '可提交下载 / 校验操作恢复这项资产。'
                          : '当前未开放恢复操作。'}
                      </div>
                    {:else if actions.previewKind === 'image'}
                      <img
                        src={assetArchiveUrl(asset.id)}
                        alt={detail.title || `${asset.kind} 预览`}
                        on:error={() => markPreviewFailed(asset.id)}
                      />
                    {:else if actions.previewKind === 'video'}
                      <!-- svelte-ignore a11y_media_has_caption -->
                      <video
                        src={assetArchiveUrl(asset.id)}
                        controls
                        preload="metadata"
                        on:error={() => markPreviewFailed(asset.id)}
                      ></video>
                    {:else if actions.previewKind === 'audio'}
                      <audio
                        src={assetArchiveUrl(asset.id)}
                        controls
                        preload="metadata"
                        on:error={() => markPreviewFailed(asset.id)}
                      ></audio>
                    {/if}
                  </div>
                {/if}
              </article>
            {/each}
          </div>
        {/if}
      </section>
    </div>
  {/if}
</Modal>

<style>
  .compact-filters {
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  .search-field {
    display: flex;
    width: 205px;
    min-height: 32px;
    align-items: center;
    gap: 7px;
    border: 1px solid var(--border-strong);
    border-radius: 6px;
    padding: 5px 9px;
    background: #fff;
    color: var(--text-muted);
  }

  .search-field:focus-within {
    border-color: #78a3f5;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.09);
  }

  .search-field input {
    min-width: 0;
    border: 0;
    outline: 0;
    background: transparent;
    color: var(--text);
    font-size: 11px;
  }

  .filter-select {
    width: auto;
    min-height: 32px;
    padding-top: 4px;
    padding-bottom: 4px;
    font-size: 11px;
  }

  .active-scope {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 9px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--accent-soft);
    color: #31517f;
    font-size: 12px;
  }

  .content-identity {
    display: flex;
    min-width: 270px;
    align-items: center;
    gap: 10px;
  }

  .kind-icon {
    display: inline-flex;
    width: 32px;
    height: 32px;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 7px;
    background: #fafbfd;
    color: #61718a;
  }

  .detail-link {
    display: block;
    border: 0;
    padding: 0;
    background: transparent;
    color: var(--text);
    font-size: inherit;
    font-weight: 570;
    text-align: left;
    cursor: pointer;
  }

  .detail-link:hover,
  .author-link:hover {
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .content-title {
    max-width: 380px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .source-link {
    display: inline-flex;
    width: 30px;
    height: 30px;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    color: #718096;
  }

  .source-link:hover {
    background: #f1f5f9;
    color: #2563eb;
  }

  .loading-rows,
  .detail-loading {
    display: grid;
    gap: 8px;
    padding: 12px 14px;
  }

  .loading-rows div {
    height: 50px;
  }

  .detail-loading {
    padding: 0;
  }

  .detail-loading div {
    height: 54px;
  }

  .list-error {
    margin: 16px;
  }

  .detail-stack {
    display: grid;
    gap: 20px;
  }

  .section-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 9px;
  }

  .section-heading h3 {
    margin: 0;
    font-size: 13px;
    font-weight: 630;
  }

  .section-heading > span {
    color: var(--text-muted);
    font-size: 11px;
  }

  .body-text {
    max-height: 260px;
    margin: 0;
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 13px 14px;
    background: #fafbfd;
    color: #344158;
    font-size: 12.5px;
    line-height: 1.75;
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  }

  .detail-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0 24px;
  }

  .detail-facts .key-value-row {
    grid-template-columns: minmax(90px, 0.65fr) minmax(0, 1.35fr);
  }

  .asset-list {
    display: grid;
    gap: 9px;
  }

  .asset-card {
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 9px;
    background: #fff;
  }

  .asset-card-main {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 11px 12px 7px;
  }

  .asset-card-main strong,
  .asset-card-main span {
    display: block;
  }

  .asset-card-main strong {
    color: var(--text);
    font-size: 12px;
  }

  .asset-card-main div > span {
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 11px;
  }

  .asset-card-actions {
    display: flex;
    gap: 5px;
    padding: 0 12px 11px;
    flex-wrap: wrap;
  }

  .preview-frame {
    padding: 12px;
    border-top: 1px solid var(--border);
    background: #f7f9fc;
  }

  .preview-frame img,
  .preview-frame video {
    display: block;
    width: 100%;
    max-height: 420px;
    border-radius: 7px;
    background: #101827;
    object-fit: contain;
  }

  .preview-frame audio {
    display: block;
    width: 100%;
  }

  .detail-empty {
    border: 1px dashed var(--border-strong);
    border-radius: 8px;
    padding: 24px;
    color: var(--text-muted);
    font-size: 12px;
    text-align: center;
  }

  @media (max-width: 1180px) {
    .compact-filters {
      max-width: 620px;
    }

    .content-table {
      min-width: 920px;
    }
  }

  @media (max-width: 720px) {
    .compact-filters,
    .search-field,
    .filter-select {
      width: 100%;
    }

    .active-scope {
      align-items: flex-start;
    }

    .detail-facts {
      grid-template-columns: 1fr;
    }

    .asset-card-main {
      align-items: flex-start;
    }
  }
</style>
