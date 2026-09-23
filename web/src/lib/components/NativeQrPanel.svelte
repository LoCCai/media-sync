<script lang="ts">
  import { onDestroy } from 'svelte';
  import { LoaderCircle, QrCode, RefreshCw } from '@lucide/svelte';

  import { NativeQrRelayMonitor, nativeQrRead, type NativeQrView } from '$lib/api/native-qr-relay';

  const POLL_INTERVAL_MS = 2000;

  let active = false;
  let timer: ReturnType<typeof setInterval> | null = null;
  let monitor: NativeQrRelayMonitor | null = null;
  let view: NativeQrView = {
    state: 'waiting',
    imageUrl: '',
    hint: '尚未开始读取；点击下方按钮并回到 /crawler/ 页面发起登录。',
    ageSeconds: null
  };

  function apply(next: NativeQrView): void {
    view = next;
  }

  export function start(): void {
    if (active) return;
    active = true;
    monitor = new NativeQrRelayMonitor({
      readQr: nativeQrRead(),
      changed: apply
    });
    void monitor.poll();
    timer = setInterval(() => void monitor?.poll(), POLL_INTERVAL_MS);
  }

  export function stop(): void {
    active = false;
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
    monitor?.dispose();
    monitor = null;
    view = {
      state: 'waiting',
      imageUrl: '',
      hint: '尚未开始读取；点击下方按钮并回到 /crawler/ 页面发起登录。',
      ageSeconds: null
    };
  }

  function toggle(): void {
    if (active) stop();
    else start();
  }

  onDestroy(stop);
</script>

<div class="qr-panel" data-testid="native-qr-panel">
  <div class="qr-head">
    <QrCode size={16} />
    <strong>原生登录二维码</strong>
    <button class="button small secondary" type="button" on:click={toggle}>
      {#if active}<LoaderCircle class="spin" size={13} />{:else}<RefreshCw size={13} />{/if}
      {active ? '停止读取' : '显示登录二维码'}
    </button>
  </div>
  {#if active}
    <div class="qr-body" data-state={view.state}>
      {#if view.imageUrl}
        <img src={view.imageUrl} alt="原生登录二维码" class="qr-image" />
      {:else}
        <div class="qr-placeholder"><LoaderCircle class="spin" size={26} /></div>
      {/if}
      <p class="qr-hint" data-testid="native-qr-hint">{view.hint}</p>
      {#if view.ageSeconds !== null}
        <p class="qr-age">距上次读取到二维码：{view.ageSeconds} 秒（180 秒时效）</p>
      {/if}
    </div>
  {:else}
    <p class="qr-hint idle">
      该面板只读取原生爬虫页面转发出来的二维码（180 秒时效，2 秒轮询），不会替你发起或重试登录。
    </p>
  {/if}
</div>

<style>
  .qr-panel {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-subtle);
    padding: 12px 14px;
  }

  .qr-head {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .qr-head strong {
    flex: 1;
    font-size: 12px;
    color: var(--text);
  }

  .qr-body {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
  }

  .qr-image {
    width: min(240px, 100%);
    height: auto;
    image-rendering: pixelated;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: #fff;
  }

  .qr-placeholder {
    display: flex;
    width: min(240px, 100%);
    height: 180px;
    align-items: center;
    justify-content: center;
    border: 1px dashed var(--border);
    border-radius: var(--radius);
    color: var(--text-secondary);
  }

  .qr-body[data-state='guidance'] .qr-placeholder {
    border-color: var(--danger, #c0392b);
  }

  .qr-hint {
    margin: 0;
    font-size: 11px;
    color: var(--text-secondary);
    text-align: center;
  }

  .qr-age {
    margin: 0;
    font-size: 10px;
    color: var(--text-secondary);
  }
</style>
