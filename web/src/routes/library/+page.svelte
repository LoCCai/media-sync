<script lang="ts">
  import { onMount } from 'svelte';
  import { Archive, Database, Film, FolderCheck, RefreshCw, Send } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import { toast } from '$lib/stores/toast';
  import type { LibraryAuthor, Settings, StartedOperation } from '$lib/types/api';
  import { formatDate, PLATFORM_META, shortId } from '$lib/utils/format';

  let authors: LibraryAuthor[] = [];
  let settings: Settings | null = null;
  let loading = true;
  let acting = '';
  let error = '';

  $: totalContent = authors.reduce((sum, item) => sum + item.content_count, 0);
  $: totalAssets = authors.reduce((sum, item) => sum + item.asset_count, 0);
  $: archivedAssets = authors.reduce((sum, item) => sum + item.archived_count, 0);
  $: exportedContent = authors.reduce((sum, item) => sum + item.exported_count, 0);

  async function load(): Promise<void> {
    loading = true;
    error = '';
    try {
      [authors, settings] = await Promise.all([
        api<LibraryAuthor[]>('/api/v1/library?limit=500'),
        api<Settings>('/api/v1/settings')
      ]);
    } catch (caught) {
      error = apiMessage(caught);
    } finally {
      loading = false;
    }
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

  function percent(done: number, total: number): number {
    return total ? Math.min(100, Math.round((done / total) * 100)) : 0;
  }

  onMount(() => void load());
</script>

<div class="page">
  <PageHeader title="媒体库" description="按作者查看归档完整度，并发布到 Emby / Jellyfin 目录。">
    <svelte:fragment slot="actions"
      ><button class="button secondary" type="button" on:click={load} disabled={loading}
        ><RefreshCw class={loading ? 'spin' : ''} size={15} />刷新</button
      ></svelte:fragment
    >
  </PageHeader>

  <section class="summary-grid library-summary">
    <div class="summary-item">
      <span class="summary-label">作者<Database size={16} /></span><strong class="summary-value"
        >{authors.length}</strong
      ><span class="summary-hint">媒体库顶层实体</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">内容<Film size={16} /></span><strong class="summary-value"
        >{totalContent}</strong
      ><span class="summary-hint">已写入内容目录</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">归档资产<Archive size={16} /></span><strong class="summary-value"
        >{archivedAssets}</strong
      ><span class="summary-hint">共 {totalAssets} 个资产</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">导出记录<FolderCheck size={16} /></span><strong class="summary-value"
        >{exportedContent}</strong
      ><span class="summary-hint">成功发布的内容</span>
    </div>
  </section>

  {#if settings}
    <div class="notice">
      <FolderCheck size={17} />
      <div>
        <strong class="notice-title">媒体库输出目录</strong><span class="mono">{settings.export_dir}</span>
      </div>
    </div>
  {/if}

  <Panel title="作者媒体库" description="导出会按当前 source fingerprint 幂等更新" flush>
    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(4) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if authors.length === 0}
      <EmptyState title="媒体库还是空的" description="完成订阅同步和资产下载后，可按作者发布到媒体库目录。">
        <a class="button secondary small" href="/subscriptions">查看订阅</a>
      </EmptyState>
    {:else}
      <div class="table-wrap">
        <table class="data-table library-table">
          <thead
            ><tr
              ><th>作者</th><th>内容</th><th>归档进度</th><th>已发布</th><th>最近内容</th><th class="actions"
                >操作</th
              ></tr
            ></thead
          >
          <tbody>
            {#each authors as author}
              <tr>
                <td
                  ><div class="inline-identity">
                    <PlatformMark platform={author.platform} />
                    <div>
                      <span class="cell-main">{author.display_name}</span><span class="cell-sub"
                        >{PLATFORM_META[author.platform].name} · {author.remote_id}</span
                      >
                    </div>
                  </div></td
                >
                <td
                  ><span class="cell-main">{author.content_count}</span><span class="cell-sub">条内容</span
                  ></td
                >
                <td
                  ><div class="archive-progress">
                    <div>
                      <span>{author.archived_count} / {author.asset_count}</span><span
                        >{percent(author.archived_count, author.asset_count)}%</span
                      >
                    </div>
                    <div class="progress-track">
                      <div
                        class="progress-bar"
                        style={`width:${percent(author.archived_count, author.asset_count)}%`}
                      ></div>
                    </div>
                  </div></td
                >
                <td>{author.exported_count} 条</td>
                <td>{formatDate(author.last_published_at)}</td>
                <td class="actions"
                  ><button
                    class="button secondary small"
                    type="button"
                    on:click={() => exportAuthor(author)}
                    disabled={!!acting}
                    ><Send size={14} />{acting === author.author_id ? '启动中…' : '导出 / 更新'}</button
                  ></td
                >
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </Panel>
</div>

<style>
  .archive-progress {
    width: 170px;
  }

  .archive-progress > div:first-child {
    display: flex;
    justify-content: space-between;
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

  @media (max-width: 880px) {
    .library-table {
      min-width: 850px;
    }
  }
</style>
