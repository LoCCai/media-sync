<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { api } from '$lib/api/client';
  import {
    COOKIE_LOGIN_FOLLOW_UP,
    CookieLoginController,
    cookieLoginEligibility,
    initialCookieLoginView,
    type CookieLoginResult
  } from '$lib/api/cookie-login';
  import Modal from './Modal.svelte';
  import { mediaCrawlerGate, onboardingAccepted, resetOnboarding } from '$lib/stores/onboarding';
  import { operatorAuth } from '$lib/stores/operator-auth';
  import type { Account, PlatformCapability } from '$lib/types/api';
  import { shortId } from '$lib/utils/format';

  export let open = false;
  export let account: Account;
  export let capability: PlatformCapability | null = null;
  const dispatch = createEventDispatcher<{ saved: CookieLoginResult }>();
  let cookie = '';
  let inputElement: HTMLTextAreaElement | undefined;
  let replaceConfirmed = false;
  let formNotice = '';
  let view = initialCookieLoginView();
  let contextKey = '';
  let notifiedOperation = '';
  const controller = new CookieLoginController(
    {
      licenseConfirmed: () => $onboardingAccepted,
      session: () => ({ epoch: $operatorAuth.epoch, authenticated: $operatorAuth.phase === 'authenticated' }),
      start: (scope, candidate, signal) => {
        try {
          return api(`/api/v1/accounts/${scope.account_id}/cookie-login`, {
            method: 'POST',
            signal,
            body: JSON.stringify({
              cookie: candidate,
              platform: scope.platform,
              expected_auth_revision: scope.expected_auth_revision,
              frontend_generation: scope.frontend_generation,
              ...mediaCrawlerGate()
            })
          });
        } finally {
          candidate = '';
        }
      },
      read: (id, signal) => api(`/api/v1/operations/${id}`, { signal })
    },
    (next) => {
      view = next;
      if (open && next.phase === 'saved' && next.result && next.operation_id !== notifiedOperation) {
        notifiedOperation = next.operation_id ?? '';
        dispatch('saved', next.result);
      }
    }
  );

  $: eligibility = cookieLoginEligibility(account, capability);
  $: busy = view.phase === 'submitting' || view.phase === 'checking';
  $: requiresReplacement = account.auth_status === 'authenticated';
  $: synchronize(account, capability, open, $operatorAuth.epoch, $operatorAuth.phase);

  function clearInput(): void {
    cookie = '';
    if (inputElement) inputElement.value = '';
  }
  function synchronize(
    current: Account,
    currentCapability: PlatformCapability | null,
    visible: boolean,
    epoch: number,
    phase: string
  ): void {
    const key = JSON.stringify([
      visible,
      current.id,
      current.platform,
      current.auth_revision,
      currentCapability?.pasted_cookie_login,
      epoch,
      phase
    ]);
    if (key === contextKey) return;
    contextKey = key;
    clearInput();
    replaceConfirmed = false;
    formNotice = '';
    controller.setContext(visible && phase === 'authenticated' ? current : null, currentCapability, epoch);
  }
  function submit(): void {
    let candidate = cookie;
    clearInput();
    formNotice = '';
    try {
      if (eligibility || (requiresReplacement && !replaceConfirmed)) {
        formNotice = eligibility || '请明确确认替换当前认证；本次未发起请求。';
        return;
      }
      void controller.submit(candidate);
    } finally {
      candidate = '';
    }
  }
  function close(): void {
    clearInput();
    controller.setContext(null, null, $operatorAuth.epoch);
    open = false;
  }
  onDestroy(() => {
    clearInput();
    controller.dispose();
  });
</script>

<Modal
  bind:open
  title={`粘贴 Cookie · ${account.display_name}`}
  description="仅在明确点击后校验并保存，不扫码、不采集内容。"
>
  <div class="cookie-dialog">
    <p>
      粘贴浏览器请求中的 <code>Cookie</code> 头值（<code>名称=值; 名称=值</code>），不要包含
      <code>Cookie:</code>
      前缀、<code>Set-Cookie</code> 属性或 JSON 导出。最多 16 KiB、128 个唯一键值对。
    </p>
    <p>
      输入仅临时保留在页面内存中，不写入网页本地存储、不提供预览或日志回显；提交、关闭、切换账户或退出后台时清空。验证成功后由服务端私密保存供后续任务使用。
    </p>
    {#if eligibility}<div class="notice warning" role="status">{eligibility}</div>{/if}
    {#if !$onboardingAccepted}
      <div class="notice warning">请先完成首次使用与许可证确认；当前不会向平台发送 Cookie。</div>
      <button
        class="button secondary small"
        type="button"
        on:click={() => {
          close();
          resetOnboarding();
        }}>查看首次使用与许可证说明</button
      >
    {/if}
    {#if requiresReplacement}
      <div class="notice warning">
        此账户已有认证。只有本次平台校验和保存都成功，才替换当前凭据；旧文件保留。提交后结果未知时请先核对账户与任务，不要重复提交。
      </div>
      <label class="replacement-confirmation"
        ><input
          type="checkbox"
          bind:checked={replaceConfirmed}
          disabled={busy || view.phase === 'saved' || view.phase === 'unknown'}
        />我确认校验成功后替换此账户当前认证</label
      >
    {/if}
    <div class="field">
      <label for="cookie-login-input">请求 Cookie 头值</label>
      <textarea
        id="cookie-login-input"
        class="input cookie-input"
        bind:this={inputElement}
        bind:value={cookie}
        rows="5"
        autocomplete="off"
        autocapitalize="off"
        spellcheck={false}
        disabled={!!eligibility || busy || view.phase === 'saved' || view.phase === 'unknown'}
        aria-describedby="cookie-login-state"
      ></textarea>
    </div>
    <div id="cookie-login-state" role="status" aria-live="polite">
      {#if formNotice}<p class="notice warning">{formNotice}</p>{/if}
      {#if busy}<p>
          输入已清空。{view.phase === 'submitting' ? '正在提交校验请求…' : '等待此操作的校验与保存结果…'}
        </p>{/if}
      {#if view.message}<p
          class="notice"
          class:success={view.phase === 'saved'}
          class:warning={view.phase !== 'saved'}
        >
          {view.message}
        </p>{/if}
      {#if view.operation_id}<p>
          本次操作 <code>{shortId(view.operation_id)}</code> ·
          <a class="text-link" href="/jobs">核对任务记录</a>
        </p>{/if}
    </div>
    <p class="scope-note">{COOKIE_LOGIN_FOLLOW_UP}</p>
    <p class="scope-note">提交后关闭仅停止本地等待，服务端可能继续校验和保存，不等于取消或回滚。</p>
  </div>
  <svelte:fragment slot="footer">
    <button class="button secondary" type="button" on:click={close}>清空并关闭</button>
    <button
      class="button"
      type="button"
      on:click={submit}
      disabled={!!eligibility ||
        busy ||
        view.phase === 'saved' ||
        view.phase === 'unknown' ||
        (requiresReplacement && !replaceConfirmed)}
    >
      {busy ? '校验中…' : '校验并保存'}
    </button>
  </svelte:fragment>
</Modal>

<style>
  .cookie-dialog {
    display: grid;
    gap: 12px;
    font-size: 12px;
    color: var(--text-secondary);
  }
  .cookie-dialog p {
    margin: 0;
  }
  .cookie-input {
    min-height: 110px;
    resize: vertical;
    font-family: monospace;
  }
  .replacement-confirmation {
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }
  .scope-note {
    color: var(--text-muted);
    font-size: 11px;
  }
</style>
