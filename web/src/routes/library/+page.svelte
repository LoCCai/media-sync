<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import {
    Archive,
    ChevronDown,
    Database,
    Eye,
    Film,
    FolderCheck,
    Images,
    RefreshCw,
    Search,
    Send,
    Server,
    ShieldCheck
  } from '@lucide/svelte';

  import { api, apiMessage, LatestRequestGate } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Modal from '$lib/components/Modal.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { toast } from '$lib/stores/toast';
  import type {
    LibraryAuthor,
    LibraryInspection,
    MediaServerAction,
    MediaServerAuthorLookup,
    MediaServerStatus,
    Platform,
    StartedOperation
  } from '$lib/types/api';
  import { buildExplorerQuery, EXPLORER_RESULT_LIMIT } from '$lib/utils/explorer';
  import { formatBytes, formatDate, PLATFORM_META, shortId } from '$lib/utils/format';
  import {
    authorAllowsRefreshAndVerify,
    authorObservationOperationRequest,
    emptyMediaServerOperationRequest,
    libraryAllows,
    libraryFreshnessLabel,
    libraryIntegrityLabel,
    mediaServerAllows,
    mediaServerLookupPresentation,
    mediaServerPosture,
    mergeLibraryInspectionPage,
    type LibraryInspectionView
  } from '$lib/utils/library';

  let authors: LibraryAuthor[] = [];
  let loading = true;
  let acting = '';
  let error = '';
  let search = '';
  let platform: Platform | 'all' = 'all';
  let mediaServer: MediaServerStatus | null = null;
  let mediaServerError = '';
  let serverActing: MediaServerAction | '' = '';
  let authorScanActing = '';
  let inspectedAuthors: Record<string, LibraryInspection | undefined> = {};
  let selectedAuthor: LibraryAuthor | null = null;
  let inspectionView: LibraryInspectionView | null = null;
  let inspectionOpen = false;
  let inspectionLoading = false;
  let inspectionError = '';
  let lookupResult: MediaServerAuthorLookup | null = null;
  let lookupLoading = false;
  let lookupError = '';
  let mounted = false;
  let listRequest = 0;
  let lookupRequest = 0;
  const inspectionRequest = new LatestRequestGate();
  const mediaServerRequest = new LatestRequestGate();
  const mediaServerLookupRequest = new LatestRequestGate();
  let searchTimer: number | undefined;

  $: totalContent = authors.reduce((sum, item) => sum + item.content_count, 0);
  $: totalAssets = authors.reduce((sum, item) => sum + item.asset_count, 0);
  $: archivedAssets = authors.reduce((sum, item) => sum + item.archived_count, 0);
  $: exportedContent = authors.reduce((sum, item) => sum + item.exported_count, 0);
  $: hasFilters = Boolean(search.trim()) || platform !== 'all';
  $: serverPosture = mediaServerPosture(mediaServer);
  $: lookupPresentation = lookupResult ? mediaServerLookupPresentation(lookupResult) : null;
  $: serverBusy = Boolean(serverActing || authorScanActing || lookupLoading);

  async function load(): Promise<void> {
    if (!mounted) return;
    if (searchTimer !== undefined) window.clearTimeout(searchTimer);
    const request = ++listRequest;
    loading = true;
    error = '';
    try {
      const result = await api<LibraryAuthor[]>(
        buildExplorerQuery('/api/v1/library', {
          q: search,
          platform,
          limit: EXPLORER_RESULT_LIMIT
        })
      );
      if (request === listRequest) {
        authors = result;
        // A new catalogue snapshot cannot inherit or be overwritten by an older inspection.
        inspectionRequest.cancel();
        inspectionLoading = false;
        inspectionView = null;
        inspectionError = '';
        inspectedAuthors = {};
        lookupRequest += 1;
        mediaServerLookupRequest.cancel();
        lookupLoading = false;
        lookupResult = null;
        lookupError = '';
        inspectionOpen = false;
        selectedAuthor = null;
      }
    } catch (caught) {
      if (request === listRequest) error = apiMessage(caught);
    } finally {
      if (request === listRequest) loading = false;
    }
  }

  async function loadMediaServer(): Promise<void> {
    mediaServerError = '';
    const result = await mediaServerRequest.run((signal) =>
      api<MediaServerStatus>('/api/v1/media-server', { signal })
    );
    if (result.status === 'fulfilled') mediaServer = result.value;
    else if (result.status === 'rejected') mediaServerError = apiMessage(result.reason);
  }

  async function refreshAll(): Promise<void> {
    await Promise.all([load(), loadMediaServer()]);
  }

  function scheduleLoad(): void {
    if (!mounted) return;
    if (searchTimer !== undefined) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => void load(), 280);
  }

  async function exportAuthor(author: LibraryAuthor): Promise<void> {
    acting = author.author_id;
    try {
      const started = await api<StartedOperation>('/api/v1/emby/export', {
        method: 'POST',
        body: JSON.stringify({ author_id: author.author_id })
      });
      toast(`${author.display_name} 的导出已启动 · ${shortId(started.operation_id)}`);
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
    } finally {
      acting = '';
    }
  }

  async function inspectAuthor(author: LibraryAuthor): Promise<void> {
    if (inspectionLoading) return;
    lookupRequest += 1;
    mediaServerLookupRequest.cancel();
    selectedAuthor = author;
    inspectionView = null;
    inspectionError = '';
    lookupResult = null;
    lookupError = '';
    lookupLoading = false;
    inspectedAuthors = { ...inspectedAuthors, [author.author_id]: undefined };
    inspectionOpen = true;
    await loadInspectionPage(author, null);
  }

  async function loadInspectionPage(author: LibraryAuthor, cursor: string | null): Promise<void> {
    inspectionLoading = true;
    inspectionError = '';
    const result = await inspectionRequest.run((signal) => {
      const query = new URLSearchParams({ limit: '64' });
      if (cursor) query.set('cursor', cursor);
      return api<LibraryInspection>(
        `/api/v1/library/${encodeURIComponent(author.author_id)}?${query.toString()}`,
        { signal }
      );
    });
    if (result.status === 'fulfilled') {
      inspectionView = mergeLibraryInspectionPage(cursor ? inspectionView : null, result.value);
      inspectedAuthors = { ...inspectedAuthors, [author.author_id]: inspectionView.inspection };
      inspectionLoading = false;
    } else if (result.status === 'rejected') {
      inspectionError = apiMessage(result.reason);
      inspectionLoading = false;
    }
  }

  async function loadMoreInspection(): Promise<void> {
    const cursor = inspectionView?.inspection.page.next_cursor;
    if (!selectedAuthor || !cursor) return;
    await loadInspectionPage(selectedAuthor, cursor);
  }

  async function runMediaServerAction(action: MediaServerAction): Promise<void> {
    if (serverBusy || !mediaServerAllows(mediaServer, action)) return;
    serverActing = action;
    try {
      const started = await api<StartedOperation>(`/api/v1/media-server/${action}`, {
        ...emptyMediaServerOperationRequest()
      });
      toast(
        `${action === 'probe' ? '媒体服务器探测' : '只确认接受的定向刷新'}已启动 · ${shortId(started.operation_id)}`
      );
      await loadMediaServer();
    } catch (caught) {
      toast(apiMessage(caught), 'danger');
      await loadMediaServer();
    } finally {
      serverActing = '';
    }
  }

  function canRefreshAndVerify(authorId: string): boolean {
    const inspection = inspectedAuthors[authorId] ?? null;
    return authorAllowsRefreshAndVerify(inspection, mediaServer);
  }

  async function refreshAndVerify(author: LibraryAuthor): Promise<void> {
    if (serverBusy || !canRefreshAndVerify(author.author_id)) return;

    authorScanActing = author.author_id;
    // A late inspection page must not restore authorization after this mutation is accepted.
    inspectionRequest.cancel();
    inspectionLoading = false;
    lookupRequest += 1;
    mediaServerLookupRequest.cancel();
    lookupLoading = false;
    lookupResult = null;
    lookupError = '';
    try {
      const started = await api<StartedOperation>('/api/v1/media-server/scan', {
        ...authorObservationOperationRequest(author.author_id)
      });
      inspectedAuthors = { ...inspectedAuthors, [author.author_id]: undefined };
      toast(`刷新并核验已启动 · ${shortId(started.operation_id)}；请在任务中心跟踪独立观察证据。`);
      await loadMediaServer();
    } catch (caught) {
      toast(`${apiMessage(caught)} 未自动重试；请先到任务中心核对是否已有对应操作。`, 'danger');
      await loadMediaServer();
    } finally {
      authorScanActing = '';
    }
  }

  async function lookupMediaServerItem(author: LibraryAuthor): Promise<void> {
    if (
      serverBusy ||
      !mediaServer?.configuration.configured ||
      !mediaServer.configuration.operations_enabled
    ) {
      return;
    }
    const request = ++lookupRequest;
    lookupLoading = true;
    lookupError = '';
    lookupResult = null;
    const result = await mediaServerLookupRequest.run((signal) =>
      api<MediaServerAuthorLookup>(
        `/api/v1/media-server/items/by-author/${encodeURIComponent(author.author_id)}`,
        { signal },
        75_000
      )
    );
    if (request === lookupRequest) {
      lookupLoading = false;
      if (selectedAuthor?.author_id !== author.author_id) return;
      if (result.status === 'fulfilled') lookupResult = result.value;
      else if (result.status === 'rejected') lookupError = apiMessage(result.reason);
    }
  }

  function percent(done: number, total: number): number {
    return total ? Math.min(100, Math.round((done / total) * 100)) : 0;
  }

  function archiveLabel(author: LibraryAuthor): string {
    return (
      {
        empty: '无媒体',
        pending: '待归档',
        partial: '部分归档',
        complete: '完整归档'
      }[author.archive_state] ?? author.archive_state
    );
  }

  onMount(() => {
    const query = new URLSearchParams(window.location.search);
    search = (query.get('q') ?? '').trim().slice(0, 200);
    const requestedPlatform = query.get('platform');
    if (requestedPlatform && requestedPlatform in PLATFORM_META) platform = requestedPlatform as Platform;
    mounted = true;
    void refreshAll();
  });

  onDestroy(() => {
    listRequest += 1;
    inspectionRequest.cancel();
    lookupRequest += 1;
    mediaServerRequest.cancel();
    mediaServerLookupRequest.cancel();
    if (searchTimer !== undefined) window.clearTimeout(searchTimer);
  });
</script>

<div class="page">
  <PageHeader title="媒体库" description="按作者搜索媒体目录，并下钻到对应内容与资产。">
    <svelte:fragment slot="actions">
      <button class="button secondary" type="button" on:click={refreshAll} disabled={loading}>
        <RefreshCw class={loading ? 'spin' : ''} size={15} />刷新
      </button>
    </svelte:fragment>
  </PageHeader>

  <section class="summary-grid library-summary">
    <div class="summary-item">
      <span class="summary-label">当前作者<Database size={16} /></span>
      <strong class="summary-value">{authors.length}</strong>
      <span class="summary-hint">最多返回 {EXPLORER_RESULT_LIMIT} 位</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">内容<Film size={16} /></span>
      <strong class="summary-value">{totalContent}</strong>
      <span class="summary-hint">当前结果中的入库内容</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">归档资产<Archive size={16} /></span>
      <strong class="summary-value">{archivedAssets}</strong>
      <span class="summary-hint">共 {totalAssets} 个资产</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">导出记录<FolderCheck size={16} /></span>
      <strong class="summary-value">{exportedContent}</strong>
      <span class="summary-hint">成功发布的内容</span>
    </div>
  </section>

  <Panel title="Emby / Jellyfin 连接" description="只使用服务端环境变量中的固定目标与网络策略">
    {#if mediaServerError}
      <div class="notice danger">{mediaServerError}</div>
    {:else if !mediaServer}
      <div class="server-loading skeleton"></div>
    {:else}
      <div class="media-server-row">
        <span class="server-icon"><Server size={21} /></span>
        <div class="server-identity">
          <strong>{mediaServer.configuration.provider?.toUpperCase() ?? '未配置媒体服务器'}</strong>
          <span>{mediaServer.configuration.origin ?? '请在部署环境中配置固定服务器'}</span>
        </div>
        <StatusBadge status={serverPosture.tone} label={serverPosture.label} />
        <div class="server-evidence">
          <span>最近探测</span>
          <StatusBadge status={mediaServer.latest_probe?.state ?? 'not_run'} />
        </div>
        <div class="server-evidence">
          <span>最近刷新 Operation</span>
          <StatusBadge status={mediaServer.latest_scan?.state ?? 'not_run'} />
        </div>
        <div class="server-actions">
          <button
            class="button secondary small"
            type="button"
            on:click={() => runMediaServerAction('probe')}
            disabled={serverBusy || !mediaServerAllows(mediaServer, 'probe')}
          >
            <ShieldCheck size={14} />{serverActing === 'probe' ? '启动中…' : '测试连接'}
          </button>
          <button
            class="button secondary small"
            type="button"
            on:click={() => runMediaServerAction('scan')}
            disabled={serverBusy || !mediaServerAllows(mediaServer, 'scan')}
          >
            <RefreshCw class={serverActing === 'scan' ? 'spin' : ''} size={14} />{serverActing === 'scan'
              ? '启动中…'
              : '定向刷新（只确认接受）'}
          </button>
        </div>
      </div>
      {#if !mediaServer.configuration.configured}
        <div class="notice server-note">未配置时不会联网；请在设置页查看所需的只读配置姿态。</div>
      {:else if !mediaServer.configuration.operations_enabled}
        <div class="notice warning server-note">
          服务端操作门默认关闭；启用前请确认固定目标、凭据与允许 CIDR。
        </div>
      {:else}
        <div class="notice server-note">
          顶部刷新只证明服务器接受请求，不证明项目已出现、provider 任务完成或媒体可播放。
        </div>
      {/if}
    {/if}
  </Panel>

  <Panel title="作者媒体库" description={`${authors.length} 条服务端结果`} flush>
    <svelte:fragment slot="actions">
      <div class="filters library-filters">
        <div class="search-field">
          <Search size={14} />
          <input
            bind:value={search}
            on:input={scheduleLoad}
            aria-label="搜索作者"
            placeholder="作者名称或标识"
          />
        </div>
        <select class="select filter-select" bind:value={platform} on:change={load} aria-label="平台筛选">
          <option value="all">全部平台</option>
          {#each Object.entries(PLATFORM_META) as [value, meta]}
            <option {value}>{meta.name}</option>
          {/each}
        </select>
      </div>
    </svelte:fragment>

    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(4) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if authors.length === 0}
      <EmptyState
        title={hasFilters ? '没有匹配作者' : '媒体库还是空的'}
        description={hasFilters
          ? '调整搜索或平台筛选后再试。'
          : '完成订阅同步和资产下载后，可按作者发布到媒体库目录。'}
      >
        {#if !hasFilters}<a class="button secondary small" href="/subscriptions">查看订阅</a>{/if}
      </EmptyState>
    {:else}
      <div class="table-wrap">
        <table class="data-table library-table">
          <thead>
            <tr
              ><th>作者</th><th>内容</th><th>归档进度</th><th>已发布</th><th>最近内容</th><th class="actions"
                >操作</th
              ></tr
            >
          </thead>
          <tbody>
            {#each authors as author}
              <tr>
                <td>
                  <div class="inline-identity">
                    <PlatformMark platform={author.platform} />
                    <div>
                      <a
                        class="cell-main author-link"
                        href={`/contents?author_id=${encodeURIComponent(author.author_id)}`}
                      >
                        {author.display_name}
                      </a>
                      <span class="cell-sub">{PLATFORM_META[author.platform].name} · {author.remote_id}</span>
                    </div>
                  </div>
                </td>
                <td>
                  <a class="count-link" href={`/contents?author_id=${encodeURIComponent(author.author_id)}`}>
                    <span class="cell-main">{author.content_count}</span><span class="cell-sub">条内容</span>
                  </a>
                </td>
                <td>
                  <a
                    class="archive-progress"
                    href={`/assets?author_id=${encodeURIComponent(author.author_id)}`}
                  >
                    <div>
                      <span>{author.archived_count} / {author.asset_count}</span>
                      <span
                        >{archiveLabel(author)} · {percent(author.archived_count, author.asset_count)}%</span
                      >
                    </div>
                    <div class="progress-track">
                      <div
                        class="progress-bar"
                        style={`width:${percent(author.archived_count, author.asset_count)}%`}
                      ></div>
                    </div>
                  </a>
                </td>
                <td>{author.exported_count} 条</td>
                <td>{formatDate(author.last_published_at)}</td>
                <td class="actions">
                  <div class="row-actions">
                    <a
                      class="button ghost small"
                      href={`/contents?author_id=${encodeURIComponent(author.author_id)}`}
                    >
                      <Film size={14} />内容
                    </a>
                    <a
                      class="button ghost small"
                      href={`/assets?author_id=${encodeURIComponent(author.author_id)}`}
                    >
                      <Images size={14} />资产
                    </a>
                    <button
                      class="button secondary small"
                      type="button"
                      on:click={() => inspectAuthor(author)}
                      disabled={inspectionLoading}><Eye size={14} />检查媒体树</button
                    >
                    {#if canRefreshAndVerify(author.author_id)}
                      <button
                        class="button secondary small"
                        type="button"
                        on:click={() => refreshAndVerify(author)}
                        disabled={serverBusy}
                      >
                        <RefreshCw
                          class={authorScanActing === author.author_id ? 'spin' : ''}
                          size={14}
                        />刷新并核验
                      </button>
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

  <div class="notice deferred-note">
    <FolderCheck size={17} />“已接受”不等于“已观察”；“已观察”不等于 provider task completion，也不等于
    playable。本页只呈现完整精确查找与持久观察证据，不会把离线测试显示为真人通过。
  </div>
</div>

<Modal
  bind:open={inspectionOpen}
  title={selectedAuthor ? `${selectedAuthor.display_name} · 受管媒体树` : '受管媒体树'}
  description="数据库发布链授权、manifest 绑定且有界的只读检查；不显示宿主路径或来源 URL"
  wide
>
  {#if inspectionError}
    <div class="notice danger inspection-error">{inspectionError}</div>
  {/if}
  {#if inspectionLoading && !inspectionView}
    <div class="inspection-loading"><RefreshCw class="spin" size={20} />正在校验受管文件…</div>
  {:else if inspectionView}
    {@const inspection = inspectionView.inspection}
    <section class="inspection-status">
      <div>
        <span>新鲜度</span>
        <StatusBadge status={inspection.freshness} label={libraryFreshnessLabel(inspection.freshness)} />
      </div>
      <div>
        <span>完整性</span>
        <StatusBadge status={inspection.integrity} label={libraryIntegrityLabel(inspection.integrity)} />
      </div>
      <div>
        <span>受管文件</span>
        <strong>{inspectionView.files.length} / {inspection.publication?.managed_file_count ?? 0}</strong>
      </div>
      <div>
        <span>本页读取</span>
        <strong>{formatBytes(inspection.page.bytes_read)}</strong>
      </div>
    </section>

    {#if inspection.freshness_reason_code || inspection.integrity_reason_code}
      <div
        class:danger={['drifted', 'inconsistent'].includes(inspection.integrity)}
        class="notice inspection-reason"
      >
        <span class="mono">{inspection.integrity_reason_code ?? inspection.freshness_reason_code}</span>
      </div>
    {/if}

    {#if inspection.publication}
      <dl class="publication-facts">
        <div>
          <dt>发布 Job</dt>
          <dd class="mono">{shortId(inspection.publication.job_id)}</dd>
        </div>
        <div>
          <dt>布局版本</dt>
          <dd>{inspection.publication.layout_version}</dd>
        </div>
        <div>
          <dt>Manifest</dt>
          <dd class="mono">{shortId(inspection.publication.manifest_sha256)}</dd>
        </div>
        <div>
          <dt>Tree</dt>
          <dd class="mono">{shortId(inspection.publication.tree_sha256)}</dd>
        </div>
      </dl>
    {/if}

    {#if lookupError}
      <div class="notice danger inspection-reason">{lookupError}</div>
    {:else if lookupLoading}
      <div class="inspection-loading"><RefreshCw class="spin" size={18} />正在执行有界精确查找…</div>
    {:else if lookupResult && lookupPresentation}
      <section class="server-lookup-evidence">
        <div class="section-heading">
          <div>
            <span>媒体服务器项目快照</span>
            <strong>{lookupResult.provider.toUpperCase()} · {formatDate(lookupResult.observed_at)}</strong>
          </div>
          <StatusBadge status={lookupPresentation.tone} label={lookupPresentation.label} />
        </div>
        <p>{lookupPresentation.detail}</p>
        {#if lookupResult.lookup_state === 'matched'}
          <div class="notice warning">
            项目在当前快照中已经存在，因此严格的 absent-to-unique-match
            验证可能在发送刷新前停止；如只需手动刷新，请使用页面顶部“只确认接受”的动作。
          </div>
        {/if}
      </section>
    {/if}

    {#if inspectionView.files.length === 0}
      <EmptyState
        title={inspection.publication ? '本页没有可显示文件' : '作者尚未发布'}
        description={inspection.publication
          ? '检查预算可能在读取首个文件前耗尽；可根据状态重新检查。'
          : '只有后端允许时，才可从本窗口启动作者导出。'}
      />
    {:else}
      <div class="table-wrap inspection-files-wrap">
        <table class="data-table inspection-files">
          <thead><tr><th>逻辑相对路径</th><th>大小</th><th>SHA-256</th></tr></thead>
          <tbody>
            {#each inspectionView.files as file}
              <tr>
                <td class="mono relative-path">{file.relative_path}</td>
                <td>{formatBytes(file.size_bytes)}</td>
                <td class="mono">{shortId(file.sha256)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}

    <div class="notice protected-note">
      <ShieldCheck size={17} />{inspection.user_changes_protected
        ? '用户修改保护已开启：检查不会修复、删除或覆盖文件。'
        : '未确认用户修改保护。'}
    </div>
  {/if}

  <svelte:fragment slot="footer">
    {#if selectedAuthor && inspectionView?.inspection.publication && mediaServer?.configuration.configured}
      <button
        class="button secondary"
        type="button"
        on:click={() => lookupMediaServerItem(selectedAuthor!)}
        disabled={serverBusy || !mediaServer.configuration.operations_enabled}
      >
        <ShieldCheck size={14} />{lookupLoading ? '查找中…' : '检查服务器项目'}
      </button>
    {/if}
    {#if selectedAuthor && canRefreshAndVerify(selectedAuthor.author_id)}
      <button
        class="button"
        type="button"
        on:click={() => refreshAndVerify(selectedAuthor!)}
        disabled={serverBusy}
      >
        <RefreshCw class={authorScanActing === selectedAuthor.author_id ? 'spin' : ''} size={14} />刷新并核验
      </button>
    {/if}
    {#if selectedAuthor && inspectionView && libraryAllows(inspectionView.inspection, 'export_author')}
      <button class="button" type="button" on:click={() => exportAuthor(selectedAuthor!)} disabled={!!acting}
        ><Send size={14} />{acting === selectedAuthor.author_id ? '启动中…' : '导出 / 更新'}</button
      >
    {/if}
    {#if inspectionView?.inspection.page.next_cursor}
      <button
        class="button secondary"
        type="button"
        on:click={loadMoreInspection}
        disabled={inspectionLoading}
        ><ChevronDown size={14} />{inspectionLoading ? '校验中…' : '继续校验下一页'}</button
      >
    {/if}
    <button class="button secondary" type="button" on:click={() => (inspectionOpen = false)}>关闭</button>
  </svelte:fragment>
</Modal>

<style>
  .server-loading {
    height: 58px;
  }

  .media-server-row {
    display: grid;
    grid-template-columns: auto minmax(180px, 1fr) auto auto auto auto;
    align-items: center;
    gap: 13px;
  }

  .server-icon {
    display: inline-flex;
    width: 42px;
    height: 42px;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 9px;
    background: #f8fafc;
    color: #536984;
  }

  .server-identity,
  .server-evidence {
    display: grid;
    gap: 3px;
  }

  .server-identity strong {
    color: var(--text);
    font-size: 13px;
  }

  .server-identity span,
  .server-evidence > span {
    color: var(--text-muted);
    font-size: 10.5px;
  }

  .server-actions {
    display: flex;
    gap: 5px;
  }

  .server-note {
    margin-top: 13px;
  }

  .library-filters {
    flex-wrap: nowrap;
  }

  .search-field {
    display: flex;
    width: 210px;
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

  .author-link:hover,
  .count-link:hover .cell-main {
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .archive-progress {
    display: block;
    width: 210px;
    border-radius: 5px;
  }

  .archive-progress:hover {
    opacity: 0.78;
  }

  .archive-progress > div:first-child {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 5px;
    color: #59677c;
    font-size: 10.5px;
  }

  .archive-progress .progress-bar {
    background: #4c617e;
  }

  .actions {
    text-align: right !important;
  }

  .row-actions {
    display: flex;
    justify-content: flex-end;
    gap: 3px;
    flex-wrap: nowrap;
  }

  .loading-rows {
    display: grid;
    gap: 2px;
    padding: 12px 14px;
  }

  .loading-rows div {
    height: 50px;
  }

  .list-error {
    margin: 16px;
  }

  .deferred-note {
    align-items: center;
  }

  .inspection-loading {
    display: flex;
    min-height: 180px;
    align-items: center;
    justify-content: center;
    gap: 9px;
    color: var(--text-muted);
  }

  .inspection-error {
    margin-bottom: 12px;
  }

  .inspection-status {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
  }

  .inspection-status > div {
    display: grid;
    gap: 7px;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 11px;
    background: #fafbfd;
  }

  .inspection-status span:first-child,
  .publication-facts dt {
    color: var(--text-muted);
    font-size: 10.5px;
  }

  .inspection-status strong {
    font-size: 12px;
  }

  .inspection-reason,
  .protected-note {
    margin-top: 12px;
  }

  .publication-facts {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
    margin: 12px 0;
  }

  .publication-facts > div {
    min-width: 0;
    border-bottom: 1px solid var(--border);
    padding: 8px 4px;
  }

  .publication-facts dd {
    margin: 4px 0 0;
    color: var(--text-secondary);
    font-size: 11px;
  }

  .server-lookup-evidence {
    display: grid;
    gap: 10px;
    margin: 12px 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    background: #fafbfd;
  }

  .server-lookup-evidence .section-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .server-lookup-evidence .section-heading > div {
    display: grid;
    gap: 3px;
  }

  .server-lookup-evidence .section-heading span,
  .server-lookup-evidence p {
    color: var(--text-muted);
    font-size: 11px;
  }

  .server-lookup-evidence p {
    margin: 0;
    line-height: 1.65;
  }

  .inspection-files-wrap {
    max-height: 360px;
    border: 1px solid var(--border);
    border-radius: 8px;
  }

  .inspection-files {
    min-width: 680px;
  }

  .relative-path {
    max-width: 440px;
    overflow-wrap: anywhere;
  }

  @media (max-width: 980px) {
    .library-table {
      min-width: 960px;
    }

    .media-server-row {
      grid-template-columns: auto minmax(180px, 1fr) auto auto;
    }

    .server-actions {
      grid-column: 2 / -1;
    }
  }

  @media (max-width: 720px) {
    .library-filters,
    .search-field,
    .filter-select {
      width: 100%;
    }

    .library-filters {
      flex-wrap: wrap;
    }

    .media-server-row,
    .inspection-status,
    .publication-facts {
      grid-template-columns: 1fr 1fr;
    }

    .server-icon {
      display: none;
    }

    .server-actions {
      grid-column: 1 / -1;
    }
  }
</style>
