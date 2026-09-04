<script lang="ts">
  import { onMount } from 'svelte';
  import { Archive, ExternalLink, FileText, Image, RefreshCw, Search, Video } from '@lucide/svelte';

  import { api, apiMessage } from '$lib/api/client';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Panel from '$lib/components/Panel.svelte';
  import PlatformMark from '$lib/components/PlatformMark.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import type { ContentItem, Platform } from '$lib/types/api';
  import { formatDate, PLATFORM_META, shortId } from '$lib/utils/format';

  let contents: ContentItem[] = [];
  let loading = true;
  let error = '';
  let search = '';
  let platform = 'all';
  let kind = 'all';

  $: filtered = contents.filter((item) => {
    const needle = search.trim().toLocaleLowerCase();
    const matchesSearch =
      !needle ||
      (item.title ?? '').toLocaleLowerCase().includes(needle) ||
      item.author_display_name.toLocaleLowerCase().includes(needle) ||
      item.remote_id.toLocaleLowerCase().includes(needle);
    return (
      matchesSearch &&
      (platform === 'all' || item.platform === platform) &&
      (kind === 'all' || item.kind === kind)
    );
  });
  $: archived = contents.filter(
    (item) => item.asset_count > 0 && item.archived_count === item.asset_count
  ).length;
  $: exported = contents.filter((item) => item.export_count > 0).length;

  async function load(): Promise<void> {
    loading = true;
    error = '';
    try {
      contents = await api<ContentItem[]>('/api/v1/contents?limit=500');
    } catch (caught) {
      error = apiMessage(caught);
    } finally {
      loading = false;
    }
  }

  function kindIcon(itemKind: string): typeof Video {
    if (['video', 'dynamic', 'mixed'].includes(itemKind)) return Video;
    if (['image', 'gallery'].includes(itemKind)) return Image;
    return FileText;
  }

  onMount(() => void load());
</script>

<div class="page">
  <PageHeader title="内容" description="浏览已入库内容及其归档、导出完整性。">
    <svelte:fragment slot="actions"
      ><button class="button secondary" type="button" on:click={load} disabled={loading}
        ><RefreshCw class={loading ? 'spin' : ''} size={15} />刷新</button
      ></svelte:fragment
    >
  </PageHeader>

  <section class="summary-grid content-summary">
    <div class="summary-item">
      <span class="summary-label">入库内容<FileText size={16} /></span><strong class="summary-value"
        >{contents.length}</strong
      ><span class="summary-hint">当前返回的最新内容</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">含媒体<Video size={16} /></span><strong class="summary-value"
        >{contents.filter((item) => item.asset_count > 0).length}</strong
      ><span class="summary-hint">至少发现 1 个资产</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">完整归档<Archive size={16} /></span><strong class="summary-value"
        >{archived}</strong
      ><span class="summary-hint">全部资产已校验</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">已发布<FileText size={16} /></span><strong class="summary-value"
        >{exported}</strong
      ><span class="summary-hint">存在成功导出记录</span>
    </div>
  </section>

  <Panel title="内容目录" description={`${filtered.length} 条结果`} flush>
    <svelte:fragment slot="actions">
      <div class="filters compact-filters">
        <div class="search-field">
          <Search size={14} /><input bind:value={search} aria-label="搜索内容" placeholder="搜索标题或作者" />
        </div>
        <select class="select filter-select" bind:value={platform} aria-label="平台筛选">
          <option value="all">全部平台</option>
          {#each Object.entries(PLATFORM_META) as [value, meta]}<option {value}>{meta.name}</option>{/each}
        </select>
        <select class="select filter-select" bind:value={kind} aria-label="类型筛选"
          ><option value="all">全部类型</option><option value="video">视频</option><option value="gallery"
            >图集</option
          ><option value="image">图片</option><option value="article">文章</option><option value="dynamic"
            >动态</option
          ><option value="mixed">混合</option></select
        >
      </div>
    </svelte:fragment>

    {#if error}
      <div class="notice danger list-error">{error}</div>
    {:else if loading}
      <div class="loading-rows">
        {#each Array(5) as _}<div class="skeleton"></div>{/each}
      </div>
    {:else if filtered.length === 0}
      <EmptyState
        title={contents.length ? '没有匹配内容' : '还没有入库内容'}
        description={contents.length
          ? '调整搜索或筛选条件后再试。'
          : '完成一次订阅同步后，内容会出现在这里。'}
      >
        {#if !contents.length}<a class="button secondary small" href="/jobs">前往任务队列</a>{/if}
      </EmptyState>
    {:else}
      <div class="table-wrap">
        <table class="data-table content-table">
          <thead
            ><tr><th>内容</th><th>平台 / 作者</th><th>发布时间</th><th>资产</th><th>归档</th><th>来源</th></tr
            ></thead
          >
          <tbody>
            {#each filtered as item}
              {@const KindIcon = kindIcon(item.kind)}
              <tr>
                <td>
                  <div class="content-identity">
                    <span class="kind-icon"><KindIcon size={16} /></span>
                    <div>
                      <span class="cell-main content-title"
                        >{item.title ||
                          item.body_excerpt ||
                          `${item.kind} · ${shortId(item.remote_id)}`}</span
                      ><span class="cell-sub">{item.kind} · {shortId(item.id)}</span>
                    </div>
                  </div>
                </td>
                <td
                  ><div class="inline-identity">
                    <PlatformMark platform={item.platform} />
                    <div>
                      <span class="cell-main">{item.author_display_name}</span><span class="cell-sub"
                        >{PLATFORM_META[item.platform].name}</span
                      >
                    </div>
                  </div></td
                >
                <td>{formatDate(item.published_at)}</td>
                <td
                  ><span class="cell-main">{item.archived_count} / {item.asset_count}</span><span
                    class="cell-sub">已校验 / 全部</span
                  ></td
                >
                <td
                  ><StatusBadge
                    status={item.asset_count > 0 && item.archived_count === item.asset_count
                      ? 'verified'
                      : item.asset_count
                        ? 'downloading'
                        : 'discovered'}
                    label={item.asset_count > 0 && item.archived_count === item.asset_count
                      ? '完整'
                      : item.asset_count
                        ? '处理中'
                        : '无媒体'}
                  /></td
                >
                <td
                  >{#if item.canonical_url}<a
                      class="source-link"
                      href={item.canonical_url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label="打开原始内容"><ExternalLink size={15} /></a
                    >{:else}—{/if}</td
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
  .compact-filters {
    flex-wrap: nowrap;
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

  .content-title {
    display: block;
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

  @media (max-width: 980px) {
    .compact-filters {
      display: none;
    }

    .content-table {
      min-width: 920px;
    }
  }
</style>
