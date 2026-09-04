<script lang="ts">
  import { page } from '$app/stores';
  import {
    Activity,
    Archive,
    BookOpen,
    Boxes,
    ChevronRight,
    CircleUserRound,
    ClipboardList,
    Database,
    FolderSync,
    LayoutDashboard,
    Menu,
    PanelLeftClose,
    Settings,
    UsersRound,
    X
  } from '@lucide/svelte';

  let mobileOpen = false;
  let collapsed = false;

  const groups = [
    {
      label: '总览',
      items: [{ href: '/', label: '仪表盘', icon: LayoutDashboard }]
    },
    {
      label: '采集管理',
      items: [
        { href: '/accounts', label: '平台账户', icon: CircleUserRound },
        { href: '/subscriptions', label: '创作者订阅', icon: UsersRound },
        { href: '/contents', label: '内容', icon: BookOpen }
      ]
    },
    {
      label: '归档与发布',
      items: [
        { href: '/assets', label: '资产与归档', icon: Archive },
        { href: '/library', label: '媒体库', icon: Database }
      ]
    }
  ];

  const bottomItems = [
    { href: '/jobs', label: '任务队列', icon: ClipboardList },
    { href: '/diagnostics', label: '诊断', icon: Activity },
    { href: '/settings', label: '设置', icon: Settings }
  ];

  const titles: Record<string, string> = {
    '/': '仪表盘',
    '/accounts': '平台账户',
    '/assets': '资产与归档',
    '/contents': '内容',
    '/diagnostics': '诊断',
    '/jobs': '任务队列',
    '/library': '媒体库',
    '/settings': '设置',
    '/subscriptions': '创作者订阅'
  };

  function isActive(href: string): boolean {
    return href === '/' ? $page.url.pathname === '/' : $page.url.pathname.startsWith(href);
  }

  function closeMobile(): void {
    mobileOpen = false;
  }
</script>

<svelte:head><title>{titles[$page.url.pathname] ?? 'media-sync'} · media-sync</title></svelte:head>

<div class:collapsed class="app-shell">
  {#if mobileOpen}
    <button class="sidebar-backdrop" type="button" aria-label="关闭菜单" on:click={closeMobile}></button>
  {/if}

  <aside class:mobile-open={mobileOpen} class="sidebar">
    <div class="brand-row">
      <a class="brand" href="/" on:click={closeMobile}>
        <span class="brand-mark"><FolderSync size={19} strokeWidth={2} /></span>
        <span class="brand-copy"><strong>media-sync</strong><small>创作者媒体归档</small></span>
      </a>
      <button
        class="sidebar-mobile-close mobile-only"
        type="button"
        aria-label="关闭菜单"
        on:click={closeMobile}
      >
        <X size={18} />
      </button>
    </div>

    <nav class="sidebar-nav" aria-label="主导航">
      {#each groups as group}
        <div class="nav-group">
          <span class="nav-group-label">{group.label}</span>
          {#each group.items as item}
            <a
              class:active={isActive(item.href)}
              class="nav-item"
              href={item.href}
              on:click={closeMobile}
              title={item.label}
            >
              <svelte:component this={item.icon} size={17} strokeWidth={1.75} />
              <span>{item.label}</span>
              {#if isActive(item.href)}<ChevronRight class="nav-chevron" size={14} />{/if}
            </a>
          {/each}
        </div>
      {/each}
    </nav>

    <nav class="sidebar-bottom" aria-label="系统导航">
      {#each bottomItems as item}
        <a
          class:active={isActive(item.href)}
          class="nav-item"
          href={item.href}
          on:click={closeMobile}
          title={item.label}
        >
          <svelte:component this={item.icon} size={17} strokeWidth={1.75} />
          <span>{item.label}</span>
          {#if isActive(item.href)}<ChevronRight class="nav-chevron" size={14} />{/if}
        </a>
      {/each}
    </nav>
  </aside>

  <div class="app-main">
    <header class="topbar">
      <div class="topbar-left">
        <button
          class="topbar-button mobile-only"
          type="button"
          aria-label="打开菜单"
          on:click={() => (mobileOpen = true)}
        >
          <Menu size={19} />
        </button>
        <button
          class="topbar-button desktop-only"
          type="button"
          aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
          on:click={() => (collapsed = !collapsed)}
        >
          <PanelLeftClose class={collapsed ? 'rotated' : ''} size={18} />
        </button>
        <span class="topbar-title">{titles[$page.url.pathname] ?? 'media-sync'}</span>
      </div>
      <div class="topbar-right">
        <span class="service-chip"><span></span>本机服务</span>
        <a class="topbar-link desktop-only" href="/api/docs" target="_blank" rel="noreferrer">
          <Boxes size={15} /> API
        </a>
      </div>
    </header>

    <main class="main-content"><slot /></main>
  </div>
</div>

<style>
  .app-shell {
    min-height: 100vh;
    padding-left: 236px;
    background: #fff;
    transition: padding-left 180ms ease;
  }

  .sidebar {
    position: fixed;
    z-index: 50;
    top: 0;
    bottom: 0;
    left: 0;
    display: flex;
    width: 236px;
    flex-direction: column;
    border-right: 1px solid #e4e8ee;
    background: #f6f8fb;
    transition:
      width 180ms ease,
      transform 180ms ease;
  }

  .brand-row {
    display: flex;
    height: 66px;
    flex: 0 0 auto;
    align-items: center;
    justify-content: space-between;
    padding: 0 17px;
    border-bottom: 1px solid #e4e8ee;
  }

  .brand {
    display: flex;
    min-width: 0;
    align-items: center;
    gap: 11px;
  }

  .brand-mark {
    display: inline-flex;
    width: 34px;
    height: 34px;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    border-radius: 9px;
    background: #2563eb;
    color: #fff;
    box-shadow: 0 4px 11px rgba(37, 99, 235, 0.2);
  }

  .brand-copy {
    display: flex;
    min-width: 0;
    flex-direction: column;
    line-height: 1.25;
  }

  .brand-copy strong {
    color: #172033;
    font-size: 14px;
    font-weight: 690;
    letter-spacing: -0.015em;
  }

  .brand-copy small {
    margin-top: 2px;
    color: #8792a5;
    font-size: 10px;
  }

  .sidebar-nav {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 14px 11px;
  }

  .nav-group + .nav-group {
    margin-top: 18px;
  }

  .nav-group-label {
    display: block;
    padding: 0 10px 6px;
    color: #96a0af;
    font-size: 10px;
    font-weight: 610;
  }

  .nav-item {
    position: relative;
    display: grid;
    min-height: 38px;
    grid-template-columns: 19px 1fr auto;
    align-items: center;
    gap: 9px;
    border-radius: 7px;
    padding: 8px 10px;
    color: #59677c;
    font-size: 12.5px;
    transition:
      color 120ms ease,
      background 120ms ease;
  }

  .nav-item:hover {
    background: #edf1f6;
    color: #253248;
  }

  .nav-item.active {
    background: #e7eefc;
    color: #1d4ed8;
    font-weight: 590;
  }

  :global(.nav-chevron) {
    opacity: 0.72;
  }

  .sidebar-bottom {
    flex: 0 0 auto;
    padding: 11px;
    border-top: 1px solid #e4e8ee;
  }

  .sidebar-mobile-close,
  .topbar-button {
    display: inline-flex;
    width: 34px;
    height: 34px;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: #66748a;
    cursor: pointer;
  }

  .sidebar-mobile-close:hover,
  .topbar-button:hover {
    background: #edf1f6;
    color: #26334a;
  }

  .topbar-button :global(.rotated) {
    transform: rotate(180deg);
  }

  .app-main {
    min-width: 0;
  }

  .topbar {
    position: sticky;
    z-index: 30;
    top: 0;
    display: flex;
    height: 66px;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 0 26px;
    border-bottom: 1px solid #e8ebf0;
    background: rgba(255, 255, 255, 0.94);
    backdrop-filter: blur(12px);
  }

  .topbar-left,
  .topbar-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .topbar-title {
    color: #39465b;
    font-size: 13px;
    font-weight: 580;
  }

  .service-chip {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: #6b778b;
    font-size: 11px;
  }

  .service-chip span {
    width: 7px;
    height: 7px;
    border-radius: 99px;
    background: #22c55e;
    box-shadow: 0 0 0 3px #dcfce7;
  }

  .topbar-link {
    display: inline-flex;
    min-height: 31px;
    align-items: center;
    gap: 6px;
    border: 1px solid #e1e5eb;
    border-radius: 6px;
    padding: 5px 9px;
    color: #5f6c81;
    font-size: 11px;
  }

  .topbar-link:hover {
    background: #f8fafc;
    color: #27354b;
  }

  .main-content {
    min-height: calc(100vh - 66px);
    padding: 24px 26px 42px;
    background: #fff;
  }

  .app-shell.collapsed {
    padding-left: 72px;
  }

  .app-shell.collapsed .sidebar {
    width: 72px;
  }

  .app-shell.collapsed .brand-row {
    padding: 0 18px;
  }

  .app-shell.collapsed .brand-copy,
  .app-shell.collapsed .nav-group-label,
  .app-shell.collapsed .nav-item span,
  .app-shell.collapsed :global(.nav-chevron) {
    display: none;
  }

  .app-shell.collapsed .nav-item {
    display: flex;
    justify-content: center;
    padding: 8px;
  }

  .sidebar-backdrop {
    position: fixed;
    z-index: 45;
    inset: 0;
    display: none;
    border: 0;
    background: rgba(15, 23, 42, 0.35);
  }

  @media (max-width: 840px) {
    .app-shell,
    .app-shell.collapsed {
      padding-left: 0;
    }

    .sidebar,
    .app-shell.collapsed .sidebar {
      width: 246px;
      transform: translateX(-100%);
      box-shadow: 12px 0 38px rgba(15, 23, 42, 0.16);
    }

    .sidebar.mobile-open {
      transform: translateX(0);
    }

    .sidebar-backdrop {
      display: block;
    }

    .app-shell.collapsed .brand-copy,
    .app-shell.collapsed .nav-group-label,
    .app-shell.collapsed .nav-item span,
    .app-shell.collapsed :global(.nav-chevron) {
      display: initial;
    }

    .app-shell.collapsed .nav-item {
      display: grid;
      justify-content: initial;
      padding: 8px 10px;
    }

    .topbar {
      padding: 0 16px;
    }

    .main-content {
      padding: 20px 16px 32px;
    }
  }
</style>
