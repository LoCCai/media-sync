<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import Panel from './Panel.svelte';
  import {
    OutputDirectoryController,
    OUTPUT_PLATFORMS,
    type OutputDraft,
    type OutputView
  } from '../api/output-directories';
  import { PLATFORM_META } from '../utils/format';
  import type { Platform } from '../types/api';

  const controller = new OutputDirectoryController((next) => {
    view = next;
  });
  let view: OutputView = controller.view;

  function changeRoot(event: Event): void {
    if (view.draft) controller.edit({ ...view.draft, shared_root: (event.target as HTMLInputElement).value });
  }
  function changePlatform(platform: Platform, event: Event): void {
    if (!view.draft) return;
    const value = (event.target as HTMLInputElement).value;
    controller.edit({
      ...view.draft,
      platform_overrides: { ...view.draft.platform_overrides, [platform]: value === '' ? null : value }
    });
  }
  function changeLayout(event: Event): void {
    if (view.draft)
      controller.edit({
        ...view.draft,
        layout: (event.target as HTMLSelectElement).value as OutputDraft['layout']
      });
  }
  onMount(() => void controller.load());
  onDestroy(() => controller.dispose());
</script>

<Panel
  title="自动下载 · 媒体目录"
  description="保存在共享数据库，API 与调度器读取同一份配置，无需另外导出或连接媒体服务器。"
>
  <p class="muted">
    填写容器内绝对路径，例如 /data/library。先把宿主机目录挂载到该路径，API 与 supervisor
    必须使用相同挂载和数据库。私有归档、任务和登录凭据位置不变。
  </p>
  {#if view.error}<div class="notice danger" role="alert">{view.error}</div>{/if}
  {#if view.notice}<div class="notice" role="status">{view.notice}</div>{/if}
  {#if view.draft && view.policy}
    <fieldset disabled={view.busy}>
      <label for="output-shared-root">媒体总目录</label>
      <input
        id="output-shared-root"
        class="input mono"
        maxlength="4096"
        value={view.draft.shared_root}
        on:input={changeRoot}
        autocomplete="off"
        spellcheck="false"
      />
      <label for="output-layout">默认目录布局</label>
      <select id="output-layout" class="input" value={view.draft.layout} on:change={changeLayout}>
        <option value="platform_subdirectories">总目录 / 平台 / 作者（新库推荐）</option>
        <option value="legacy_flat">总目录 / 作者（保留旧库布局）</option>
      </select>
      <p class="muted">
        已有输出或写入绑定的平台受保护，不能直接改生效路径；可通过平台覆盖保留原根目录。保存不会搬移旧文件，显式文件迁移仍待实现。路径预览不代表挂载可写或下载已成功。
      </p>
      <div class="platform-grid">
        {#each OUTPUT_PLATFORMS as platform}
          <div class="platform-path">
            <label for={`output-${platform}`}
              >{PLATFORM_META[platform].name}
              {#if view.policy.protected_platforms.includes(platform)}<span class="protected"
                  >原目录受保护</span
                >{/if}</label
            >
            <input
              id={`output-${platform}`}
              class="input mono"
              maxlength="4096"
              value={view.draft.platform_overrides[platform] ?? ''}
              on:input={(event) => changePlatform(platform, event)}
              placeholder="留空：继承总目录布局"
              autocomplete="off"
              spellcheck="false"
            />
            <span class="muted"
              >{view.preview ? '预览生效' : '当前已生效'}：<code
                >{(view.preview ?? view.policy).effective_roots[platform]}</code
              ></span
            >
          </div>
        {/each}
      </div>
      <div class="button-row">
        <button class="button secondary" type="button" on:click={() => controller.preview()}>预览路径</button>
        <button class="button" type="button" disabled={!view.preview} on:click={() => controller.save()}
          >保存目录设置</button
        >
      </div>
    </fieldset>
    <p class="muted">
      修订 {view.policy.revision} · {view.policy.initialized
        ? '已存入共享数据库'
        : '启动默认值，尚未保存或绑定'} · 修改任何字段后需要重新预览。
    </p>
  {:else if view.busy}<p class="muted">正在读取目录设置…</p>{/if}
  <button class="button secondary" type="button" disabled={view.busy} on:click={() => controller.load()}
    >重新加载设置（放弃草稿）</button
  >
</Panel>

<style>
  fieldset {
    border: 0;
    padding: 0;
    margin: 14px 0;
    min-width: 0;
  }
  label {
    display: block;
    font-size: 12px;
    margin: 12px 0 6px;
  }
  input,
  select {
    width: 100%;
  }
  .platform-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 4px 18px;
    margin-bottom: 18px;
  }
  .platform-path > span {
    display: block;
    margin-top: 6px;
    overflow-wrap: anywhere;
  }
  .protected {
    color: #8c611c;
    font-size: 11px;
  }
  .notice {
    margin-bottom: 10px;
  }
  @media (max-width: 720px) {
    .platform-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
