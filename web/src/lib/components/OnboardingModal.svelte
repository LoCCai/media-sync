<script lang="ts">
  import { Check, Database, ShieldCheck, Sparkles } from '@lucide/svelte';

  import { acceptOnboarding, onboardingAccepted, onboardingHydrated } from '$lib/stores/onboarding';
  import Modal from './Modal.svelte';

  $: open = $onboardingHydrated && !$onboardingAccepted;
</script>

<Modal
  bind:open
  title="欢迎使用 media-sync"
  description="首次使用确认 · 以后刷新页面不会重复出现"
  dismissible={false}
>
  <div class="onboarding-mark"><Sparkles size={23} strokeWidth={1.8} /></div>
  <p class="onboarding-lead">
    这是你的自托管媒体归档控制台。确认一次后，扫码登录、同步和下载会自动携带 MediaCrawler
    启用及许可证确认，不再要求每次勾选。
  </p>

  <div class="onboarding-points">
    <div><ShieldCheck size={17} /><span>MediaCrawler 仅按其非商业学习许可证用于个人环境</span></div>
    <div><Database size={17} /><span>账户会话、归档和任务数据保留在你的部署目录</span></div>
    <div><Check size={17} /><span>后端 checkout、Git blob 与运行时资格检查仍会完整执行</span></div>
  </div>

  <div class="notice warning" style="margin-top:16px">
    控制台当前无鉴权，只应发布到本机或可信内网。若需要公网访问，请先在反向代理层启用 HTTPS 与身份认证。
  </div>

  <svelte:fragment slot="footer">
    <button class="button" type="button" on:click={acceptOnboarding}>
      <Check size={16} strokeWidth={2} />
      我已知晓，进入控制台
    </button>
  </svelte:fragment>
</Modal>

<style>
  .onboarding-mark {
    display: flex;
    width: 48px;
    height: 48px;
    align-items: center;
    justify-content: center;
    margin-bottom: 15px;
    border-radius: 12px;
    background: #eff6ff;
    color: #2563eb;
  }

  .onboarding-lead {
    margin: 0;
    color: #475569;
    font-size: 13px;
    line-height: 1.72;
  }

  .onboarding-points {
    display: grid;
    gap: 10px;
    margin-top: 18px;
  }

  .onboarding-points div {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    color: #344158;
    font-size: 12px;
  }

  .onboarding-points :global(svg) {
    flex: 0 0 auto;
    margin-top: 1px;
    color: #4e6c9b;
  }
</style>
