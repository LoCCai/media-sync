<script lang="ts">
  import { LockKeyhole, LoaderCircle, LogIn, RefreshCw } from '@lucide/svelte';
  import { operatorAuth } from '$lib/stores/operator-auth';

  let credential = '';
  const messages: Record<string, string> = {
    operator_auth_required: '请登录后台。已有会话可能已经过期或被替换。',
    operator_session_expired: '后台会话已到期，请重新登录。',
    operator_logged_out: '已确认退出后台。',
    operator_login_failed: '后台凭据不正确，请核对后重试。',
    operator_login_rate_limited: '尝试次数过多，请等待一分钟后手动重试。',
    operator_origin_forbidden: '当前浏览器地址未列入允许的 Origin，请核对部署配置。',
    operator_host_forbidden: '当前 Host 未获允许，请使用已配置的后台地址。',
    operator_connection_failed: '无法确认后台连接。请检查服务后重试，不会自动重放操作。',
    operator_session_invalid: '服务器会话响应无效，后台保持锁定。',
    operator_logout_unconfirmed: '退出尚未获得服务器确认；后台已锁定，但服务器会话可能仍然有效。请重试退出。',
    operator_request_failed: '后台请求未成功，请检查服务配置后重试。'
  };

  async function login(): Promise<void> {
    const submitted = credential;
    credential = '';
    await operatorAuth.login(submitted);
  }
</script>

<svelte:head><title>后台登录 · media-sync</title></svelte:head>

<main class="login-screen">
  <section
    class="login-card"
    aria-labelledby="operator-login-title"
    aria-busy={$operatorAuth.phase === 'checking'}
  >
    <span class="login-mark"><LockKeyhole size={24} /></span>
    <p class="eyebrow">media-sync · 单操作者控制台</p>
    <h1 id="operator-login-title">登录管理后台</h1>
    <p class="intro">这是后台管理凭据，不是 Bilibili 等平台账户密码。平台登录将在进入后台后单独进行。</p>
    {#if $operatorAuth.phase === 'checking'}
      <div class="checking" role="status"><LoaderCircle class="spin" size={19} />正在核验后台会话…</div>
    {:else}
      {#if $operatorAuth.code}
        <div class="notice {$operatorAuth.phase === 'logout_unconfirmed' ? 'warning' : 'info'}" role="status">
          {messages[$operatorAuth.code] ?? '后台会话尚未确认，请重试。'}
        </div>
      {/if}
      {#if $operatorAuth.phase === 'logout_unconfirmed'}
        <button class="button" type="button" on:click={() => void operatorAuth.logout()}
          ><RefreshCw size={16} />重试退出</button
        >
      {:else}
        <form on:submit|preventDefault={login}>
          <label for="operator-credential">后台凭据</label>
          <input
            id="operator-credential"
            name="operator-credential"
            type="password"
            bind:value={credential}
            autocomplete="current-password"
            required
            maxlength="1024"
            spellcheck="false"
          />
          <button class="button" type="submit" disabled={!credential}><LogIn size={16} />登录后台</button>
        </form>
        <button class="button ghost" type="button" on:click={() => void operatorAuth.checkSession()}
          ><RefreshCw size={15} />重新检查已有会话</button
        >
      {/if}
    {/if}
    <p class="footnote">
      凭据与 CSRF 不写入浏览器存储。会话由同源 HttpOnly Cookie 管理；非回环访问须使用已配置的 HTTPS 地址。
    </p>
  </section>
</main>

<style>
  .login-screen {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 28px 18px;
    background: #f6f8fb;
  }
  .login-card {
    width: min(100%, 440px);
    border: 1px solid #e1e7ef;
    border-radius: 16px;
    padding: 32px;
    background: #fff;
    box-shadow: 0 12px 40px #1e3a5f0c;
  }
  .login-mark {
    display: inline-flex;
    padding: 12px;
    border-radius: 12px;
    background: #eff6ff;
    color: #2563eb;
  }
  .eyebrow {
    margin: 21px 0 8px;
    color: #64748b;
    font-size: 11px;
  }
  h1 {
    margin: 0 0 12px;
    font-size: 25px;
    color: #172033;
  }
  .intro,
  .footnote {
    color: #64748b;
    line-height: 1.8;
    font-size: 12px;
  }
  .intro {
    margin-bottom: 24px;
  }
  .footnote {
    margin: 24px 0 0;
    font-size: 11px;
  }
  form {
    display: grid;
    gap: 10px;
    margin: 20px 0 8px;
  }
  label {
    font-size: 12px;
    font-weight: 600;
    color: #475569;
  }
  input {
    width: 100%;
    min-height: 42px;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    padding: 8px 11px;
    font: inherit;
  }
  input:focus {
    outline: 2px solid #93c5fd;
    outline-offset: 2px;
  }
  .button {
    justify-content: center;
    min-height: 40px;
  }
  .checking {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 90px;
    color: #475569;
    font-size: 13px;
  }
</style>
