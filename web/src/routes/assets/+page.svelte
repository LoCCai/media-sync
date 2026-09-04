<script lang="ts">
  import { afterNavigate } from '$app/navigation';
  import { onDestroy } from 'svelte';
  import {
    Archive,
    Download,
    ExternalLink,
    Eye,
    FileCheck2,
    HardDrive,
    RefreshCw,
    Search,
    Send,
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
  import type {
    Asset,
    AssetDetail,
    AssetKind,
    AssetStatus,
    Platform,
    StartedOperation
  } from '$lib/types/api';
  import {
    assetActions,
    assetArchiveUrl,
    assetExplorerQueryState,
    assetRecoveryAvailable,
    assetRecoveryUrl,
    buildExplorerQuery,
    EXPLORER_RESULT_LIMIT
  } from '$lib/utils/explorer';
  import { formatBytes, formatDate, formatDateLong, PLATFORM_META, shortId } from '$lib/utils/format';

  let assets: Asset[] = [];
  let loading = true;
  let acting = '';
  let error = '';
  let search = '';
  let platform: Platform | 'all' = 'all';
  let kind: AssetKind | 'all' = 'all';
  let status: AssetStatus | 'all' = 'all';
  let archived: boolean | 'all' = 'all';
  let authorId = '';
  let contentId = '';
  let mounted = false;
  let listRequest = 0;
  let searchTimer: number | undefined;

  let detailOpen = false;
  let detailLoading = false;
  let detailError = '';
  let detail: AssetDetail | null = null;
  let selectedSummary: Asset | null = null;
  let detailRequest = 0;
  let previewOpen = false;
  let previewFailed = false;

  let exportOpen = false;
  let exportAuthorId = '';

  $: verified = assets.filter((item) => ['verified', 'exported'].includes(item.status)).length;
  $: recoverable = assets.filter((item) => assetActions(item).canDownload).length;
  $: totalBytes = assets.reduce((sum, item) => sum + (item.size_bytes ?? 0), 0);
  $: hasFilters =
    Boolean(search.trim() || authorId || contentId) ||
    platform !== 'all' ||
    kind !== 'all' ||
    status !== 'all' ||
    archived !== 'all';
  $: detailActions = detail ? assetActions(detail) : null;

  async function load(): Promise<void> {
    if (!mounted) return;
    if (searchTimer !== undefined) window.clearTimeout(searchTimer);
    const request = ++listRequest;
    loading = true;
    error = '';
    try {
      const result = await api<Asset[]>(
        buildExplorerQuery('/api/v1/assets', {
          q: search,
          platform,
          kind,
          status,
          author_id: authorId,
          content_id: contentId,
          archived,
          limit: EXPLORER_RESULT_LIMIT
        })
      );
      if (request === listRequest) assets = result;
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

  function clearScope(scope: 'author' | 'content'): void {
    if (scope === 'author') authorId = '';
    else contentId = '';
    const next = new URL(window.location.href);
    next.searchParams.delete(scope === 'author' ? 'author_id' : 'content_id');
    window.history.replaceState({}, '', `${next.pathname}${next.search}${next.hash}`);
    void load();
  }

  async function openDetail(asset: Asset): Promise<void> {
    const request = ++detailRequest;
    selectedSummary = asset;
    detail = null;
    detailError = '';
    detailLoading = true;
    detailOpen = true;
    previewOpen = false;
    previewFailed = false;
    try {
      const result = await api<AssetDetail>(`/api/v1/assets/${encodeURIComponent(asset.id)}`);
      if (request === detailRequest) detail = result;
    } catch (caught) {
      if (request === detailRequest) detailError = apiMessage(caught);
    } finally {
      if (request === detailRequest) detailLoading = false;
    }
  }

  function showPreview(): void {
    previewFailed = false;
    previewOpen = !previewOpen;
  }

  async function downloadAsset(asset: Asset): Promise<void> {
    if (!assetRecoveryAvailable(assetActions(asset))) return;
    acting = asset.id;
    try {
      const started = await api<StartedOperation>(assetRecoveryUrl(asset.id), {
        method: 'POST',
        body: JSON.stringify({ ...mediaCrawlerGate() })
      });
      toast(`资产下载 / 恢复已启动 · ${shortId(started.operation_id)}`);
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      acting = '';
    }
  }

  function downloadDetailedAsset(): void {
    if (detail) void downloadAsset(detail);
  }

  function prepareExport(asset?: Asset): void {
    exportAuthorId = asset?.author_id ?? '';
    exportOpen = true;
  }

  function prepareDetailedExport(): void {
    if (detail) prepareExport(detail);
  }

  async function exportAuthor(): Promise<void> {
    if (!exportAuthorId.trim()) {
      toast('请输入作者 UUID。', 'danger');
      return;
    }
    acting = 'export';
    try {
      const started = await api<StartedOperation>('/api/v1/emby/export', {
        method: 'POST',
        body: JSON.stringify({ author_id: exportAuthorId.trim() })
      });
      toast(`媒体库导出已启动 · ${shortId(started.operation_id)}`);
      exportOpen = false;
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      acting = '';
    }
  }

  function formatDuration(durationMs: number | null): string {
    if (durationMs === null) return '—';
    const totalSeconds = Math.max(0, Math.round(durationMs / 1_000));
    const hours = Math.floor(totalSeconds / 3_600);
    const minutes = Math.floor((totalSeconds % 3_600) / 60);
    const seconds = totalSeconds % 60;
    return hours
      ? `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
      : `${minutes}:${String(seconds).padStart(2, '0')}`;
  }

  afterNavigate(() => {
    const query = assetExplorerQueryState(new URLSearchParams(window.location.search));
    search = query.q;
    platform = query.platform;
    kind = query.kind;
    status = query.status;
    authorId = query.author_id;
    contentId = query.content_id;
    archived = query.archived;
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
  <PageHeader title="资产与归档" description="服务端筛选媒体资产，安全预览已验证归档或提交持久恢复操作。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={load} disabled={loading}>
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新
      </button>
      <button class="button" type="button" on:click={() => prepareExport()}><Send size={15} />导出作者</button
      >
    </svelte:fragment>
  </PageHeader>

  <section class="summary-grid asset-summary">
    <div class="summary-item">
      <span class="summary-label">当前结果<Archive size={16} /></span>
      <strong class="summary-value">{assets.length}</strong>
      <span class="summary-hint">最多返回 {EXPLORER_RESULT_LIMIT} 条</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">已校验<FileCheck2 size={16} /></span>
      <strong class="summary-value">{verified}</strong>
      <span class="summary-hint"
        >{assets.length ? Math.round((verified / assets.length) * 100) : 0}% 完成</span
      >
    </div>
    <div class="summary-item">
      <span class="summary-label">可恢复<Download size={16} /></span>
      <strong class="summary-value">{recoverable}</strong>
      <span class="summary-hint">由后端开放下载动作</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">已知容量<HardDrive size={16} /></span>
      <strong class="summary-value bytes">{formatBytes(totalBytes)}</strong>
      <span class="summary-hint">仅统计当前结果</span>
    </div>
  </section>

  <Panel title="资产清单" description={`${assets.length} 条服务端结果`} flush>
    <svelte:fragment slot="actions">
      <div class="filters asset-filters">
        <div class="search-field">
          <Search size={14} />
          <input
            bind:value={search}
            on:input={scheduleLoad}
            aria-label="搜索资产"
            placeholder="资产、内容或作者"
          />
        </div>
        <select class="select filter-select" bind:value={platform} on:change={load} aria-label="平台筛选">
          <option value="all">全部平台</option>
          {#each Object.entries(PLATFORM_META) as [value, meta]}
            <option {value}>{meta.name}</option>
          {/each}
        </select>
        <select class="select filter-select" bind:value={kind} on:change={load} aria-label="资产类型筛选">
          <option value="all">全部类型</option>
          <option value="image">图片</option>
          <option value="video">视频</option>
          <option value="audio">音频</option>
          <option value="cover">封面</option>
          <option value="avatar">头像</option>
          <option value="subtitle">字幕</option>
          <option value="attachment">附件</option>
        </select>
        <select class="select filter-select" bind:value={status} on:change={load} aria-label="状态筛选">
          <option value="all">全部状态</option>
          <option value="discovered">已发现</option>
          <option value="queued">排队中</option>
          <option value="downloading">下载中</option>
          <option value="downloaded">已下载</option>
          <option value="verified">已校验</option>
          <option value="exported">已导出</option>
          <option value="failed_retryable">可重试</option>
          <option value="failed_terminal">终止失败</option>
        </select>
        <select class="select filter-select" bind:value={archived} on:change={load} aria-label="归档筛选">
          <option value="all">全部归档</option>
          <option value={true}>已归档状态</option>
          <option value={false}>未归档状态</option>
        </select>
      </div>
    </svelte:fragment>

    {#if authorId || contentId}
      <div class="scope-list">
        {#if authorId}
          <span class="scope-chip">
            作者 {shortId(authorId)}
            <button type="button" on:click={() => clearScope('author')} aria-label="清除作者筛选"
              ><X size={13} /></button
            >
          </span>
        {/if}
        {#if contentId}
          <span class="scope-chip">
            内容 {shortId(contentId)}
            <button type="button" on:click={() => clearScope('content')} aria-label="清除内容筛选"
              ><X size={13} /></button
            >
          </span>
        {/if}
      </div>
    {/if}

    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(5) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if assets.length === 0}
      <EmptyState
        title={hasFilters ? '没有匹配资产' : '还没有媒体资产'}
        description={hasFilters
          ? '调整搜索或筛选条件后再试。'
          : '订阅同步发现媒体后，资产会进入下载与校验流水线。'}
      />
    {:else}
      <div class="table-wrap">
        <table class="data-table asset-table">
          <thead>
            <tr
              ><th>资产 / 内容</th><th>平台 / 作者</th><th>类型</th><th>状态</th><th>大小</th><th>校验时间</th
              ><th class="actions">操作</th></tr
            >
          </thead>
          <tbody>
            {#each assets as asset}
              {@const actions = assetActions(asset)}
              <tr>
                <td>
                  <button class="detail-link" type="button" on:click={() => openDetail(asset)}>
                    {asset.content_title || `资产 ${shortId(asset.id)}`}
                  </button>
                  <span class="cell-sub mono"
                    >{shortId(asset.id)} · 内容 {shortId(asset.content_id)} · G{asset.generation}</span
                  >
                </td>
                <td>
                  <div class="inline-identity">
                    <PlatformMark platform={asset.platform} />
                    <div>
                      <a
                        class="cell-main author-link"
                        href={`/assets?author_id=${encodeURIComponent(asset.author_id)}`}
                      >
                        {asset.author_display_name}
                      </a>
                      <span class="cell-sub">{PLATFORM_META[asset.platform].name}</span>
                    </div>
                  </div>
                </td>
                <td>
                  <span class="cell-main">{asset.kind}</span>
                  <span class="cell-sub">{asset.mime_type ?? `position ${asset.position}`}</span>
                </td>
                <td><StatusBadge status={asset.status} /></td>
                <td>{formatBytes(asset.size_bytes)}</td>
                <td>{formatDate(asset.verified_at)}</td>
                <td class="actions">
                  <div class="row-actions">
                    <button class="button ghost small" type="button" on:click={() => openDetail(asset)}>
                      <Eye size={14} />详情
                    </button>
                    {#if actions.canExportAuthor}
                      <button class="button ghost small" type="button" on:click={() => prepareExport(asset)}>
                        <Send size={14} />导出
                      </button>
                    {/if}
                    {#if assetRecoveryAvailable(actions)}
                      <button
                        class="button secondary small"
                        type="button"
                        on:click={() => downloadAsset(asset)}
                        disabled={!!acting}
                        ><Download size={14} />{acting === asset.id ? '启动中' : '下载 / 恢复'}</button
                      >
                    {/if}
                  </div>
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
  title="资产详情"
  description={selectedSummary
    ? `${PLATFORM_META[selectedSummary.platform].name} · ${shortId(selectedSummary.id)}`
    : null}
  wide
>
  {#if detailLoading}
    <div class="detail-loading">
      {#each Array(4) as _}<div class="skeleton"></div>{/each}
    </div>
  {:else if detailError}
    <div class="notice danger">{detailError}</div>
  {:else if detail && detailActions}
    <div class="detail-stack">
      <section class="asset-heading">
        <div class="inline-identity">
          <PlatformMark platform={detail.platform} />
          <div>
            <strong>{detail.content_title || detail.content.title || `${detail.kind} 资产`}</strong>
            <span>{detail.author_display_name} · {detail.kind} #{detail.position + 1}</span>
          </div>
        </div>
        <StatusBadge status={detail.status} />
      </section>

      <dl class="key-value-list detail-facts">
        <div class="key-value-row">
          <dt>媒体类型</dt>
          <dd>{detail.mime_type ?? '—'}</dd>
        </div>
        <div class="key-value-row">
          <dt>大小</dt>
          <dd>{formatBytes(detail.size_bytes)}</dd>
        </div>
        <div class="key-value-row">
          <dt>画面尺寸</dt>
          <dd>{detail.width && detail.height ? `${detail.width} × ${detail.height}` : '—'}</dd>
        </div>
        <div class="key-value-row">
          <dt>时长</dt>
          <dd>{formatDuration(detail.duration_ms)}</dd>
        </div>
        <div class="key-value-row">
          <dt>下载完成</dt>
          <dd>{formatDateLong(detail.downloaded_at)}</dd>
        </div>
        <div class="key-value-row">
          <dt>校验完成</dt>
          <dd>{formatDateLong(detail.verified_at)}</dd>
        </div>
        <div class="key-value-row">
          <dt>首次入库</dt>
          <dd>{formatDateLong(detail.created_at)}</dd>
        </div>
        <div class="key-value-row">
          <dt>最近更新</dt>
          <dd>{formatDateLong(detail.updated_at)}</dd>
        </div>
        <div class="key-value-row">
          <dt>错误代码</dt>
          <dd>{detail.last_error_code ?? '—'}</dd>
        </div>
        <div class="key-value-row checksum-row">
          <dt>SHA-256</dt>
          <dd class="mono">{detail.checksum_sha256 ?? '—'}</dd>
        </div>
      </dl>

      <section>
        <div class="section-heading">
          <div>
            <h3>归档预览</h3>
            <span>{detail.archive.eligible ? '元数据满足预览门槛' : '归档尚未就绪'}</span>
          </div>
          <div class="preview-actions">
            {#if detailActions.canPreview && detailActions.previewKind !== 'new-tab'}
              <button class="button secondary small" type="button" on:click={showPreview}>
                <Eye size={14} />{previewOpen ? '收起预览' : '内联预览'}
              </button>
            {/if}
            {#if detailActions.canPreview}
              <a class="button ghost small" href={assetArchiveUrl(detail.id)} target="_blank" rel="noreferrer"
                ><ExternalLink size={14} />新标签</a
              >
            {/if}
            {#if detailActions.canExportAuthor}
              <button class="button ghost small" type="button" on:click={prepareDetailedExport}>
                <Send size={14} />导出作者
              </button>
            {/if}
            {#if assetRecoveryAvailable(detailActions)}
              <button
                class="button secondary small"
                type="button"
                on:click={downloadDetailedAsset}
                disabled={!!acting}
                ><Download size={14} />{acting === detail.id ? '启动中…' : '下载 / 恢复'}</button
              >
            {/if}
          </div>
        </div>

        {#if previewFailed}
          <div class="notice warning preview-notice">
            归档文件缺失、损坏或不再安全，预览已关闭。{assetRecoveryAvailable(detailActions)
              ? '请提交下载 / 校验操作恢复。'
              : '当前未开放恢复操作。'}
          </div>
        {:else if !detailActions.canPreview}
          <div class="notice preview-notice">此资产当前不可预览；后端只会提供已验证且安全的归档字节。</div>
        {:else if previewOpen}
          <div class="preview-frame">
            {#if detailActions.previewKind === 'image'}
              <img
                src={assetArchiveUrl(detail.id)}
                alt={detail.content_title || `${detail.kind} 预览`}
                on:error={() => (previewFailed = true)}
              />
            {:else if detailActions.previewKind === 'video'}
              <!-- svelte-ignore a11y_media_has_caption -->
              <video
                src={assetArchiveUrl(detail.id)}
                controls
                preload="metadata"
                on:error={() => (previewFailed = true)}
              ></video>
            {:else if detailActions.previewKind === 'audio'}
              <audio
                src={assetArchiveUrl(detail.id)}
                controls
                preload="metadata"
                on:error={() => (previewFailed = true)}
              ></audio>
            {/if}
          </div>
        {/if}
      </section>

      <section class="content-reference">
        <div>
          <span>所属内容</span>
          <strong
            >{detail.content.title || `${detail.content.kind} · ${shortId(detail.content.remote_id)}`}</strong
          >
          <small>{formatDateLong(detail.content.published_at)}</small>
        </div>
        <a class="button ghost small" href={`/contents?q=${encodeURIComponent(detail.content.remote_id)}`}>
          查看这条内容
        </a>
      </section>
    </div>
  {/if}
</Modal>

<Modal bind:open={exportOpen} title="导出作者到媒体库" description="为该作者生成 Emby / Jellyfin 兼容目录。">
  <div class="field">
    <label for="export-author">作者 UUID</label>
    <input
      id="export-author"
      class="input mono"
      bind:value={exportAuthorId}
      placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    />
  </div>
  <div class="notice" style="margin-top:14px">
    <Send size={17} />导出采用暂存目录与原子发布；已有相同指纹时不会重复写入。
  </div>
  <svelte:fragment slot="footer">
    <button class="button secondary" type="button" on:click={() => (exportOpen = false)}>取消</button>
    <button class="button" type="button" on:click={exportAuthor} disabled={acting === 'export'}>
      {acting === 'export' ? '启动中…' : '开始导出'}
    </button>
  </svelte:fragment>
</Modal>

<style>
  .summary-value.bytes {
    font-size: 21px;
  }

  .asset-filters {
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  .search-field {
    display: flex;
    width: 190px;
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

  .scope-list {
    display: flex;
    gap: 7px;
    padding: 9px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--accent-soft);
    flex-wrap: wrap;
  }

  .scope-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    border: 1px solid #bfdbfe;
    border-radius: 999px;
    padding: 3px 7px 3px 9px;
    background: #fff;
    color: #31517f;
    font-size: 11px;
  }

  .scope-chip button {
    display: inline-flex;
    border: 0;
    padding: 2px;
    background: transparent;
    color: inherit;
    cursor: pointer;
  }

  .detail-link {
    max-width: 320px;
    overflow: hidden;
    border: 0;
    padding: 0;
    background: transparent;
    color: var(--text);
    font-size: inherit;
    font-weight: 570;
    text-align: left;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }

  .detail-link:hover,
  .author-link:hover {
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .actions {
    text-align: right !important;
  }

  .row-actions,
  .preview-actions {
    display: flex;
    justify-content: flex-end;
    gap: 4px;
    flex-wrap: wrap;
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

  .asset-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    border: 1px solid var(--border);
    border-radius: 9px;
    padding: 12px;
    background: #fafbfd;
  }

  .asset-heading strong,
  .asset-heading span {
    display: block;
  }

  .asset-heading strong {
    font-size: 13px;
  }

  .asset-heading div div > span {
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 11px;
  }

  .detail-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0 24px;
  }

  .detail-facts .key-value-row {
    grid-template-columns: minmax(90px, 0.65fr) minmax(0, 1.35fr);
  }

  .checksum-row {
    grid-column: 1 / -1;
  }

  .checksum-row dd {
    word-break: break-all;
  }

  .section-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
  }

  .section-heading h3,
  .section-heading span {
    display: block;
  }

  .section-heading h3 {
    margin: 0;
    font-size: 13px;
    font-weight: 630;
  }

  .section-heading div > span {
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 11px;
  }

  .preview-frame {
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: 9px;
    background: #f7f9fc;
  }

  .preview-frame img,
  .preview-frame video {
    display: block;
    width: 100%;
    max-height: 440px;
    border-radius: 7px;
    background: #101827;
    object-fit: contain;
  }

  .preview-frame audio {
    display: block;
    width: 100%;
  }

  .preview-notice {
    align-items: center;
  }

  .content-reference {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    border-top: 1px solid var(--border);
    padding-top: 15px;
  }

  .content-reference span,
  .content-reference strong,
  .content-reference small {
    display: block;
  }

  .content-reference span,
  .content-reference small {
    color: var(--text-muted);
    font-size: 11px;
  }

  .content-reference strong {
    margin: 3px 0;
    font-size: 12.5px;
  }

  @media (max-width: 1180px) {
    .asset-filters {
      max-width: 610px;
    }

    .asset-table {
      min-width: 1080px;
    }
  }

  @media (max-width: 720px) {
    .asset-filters,
    .search-field,
    .filter-select {
      width: 100%;
    }

    .detail-facts {
      grid-template-columns: 1fr;
    }

    .checksum-row {
      grid-column: auto;
    }

    .section-heading,
    .content-reference {
      align-items: flex-start;
      flex-direction: column;
    }

    .preview-actions {
      width: 100%;
      justify-content: flex-start;
    }
  }
</style>
