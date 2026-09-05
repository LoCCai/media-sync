<script lang="ts">
  import { UserRound } from '@lucide/svelte';
  import type { CreatorProfile } from '$lib/types/api';
  import {
    creatorAvatarEventMatches,
    creatorAvatarKey,
    safeCreatorAvatarUrl
  } from '$lib/utils/creator-profile';
  import { formatDateLong } from '$lib/utils/format';

  export let profile: CreatorProfile;
  export let contextKey = '';
  export let previous = false;
  export let compact = false;
  let failedKey = '';
  $: avatarUrl = safeCreatorAvatarUrl(profile);
  $: imageKey = creatorAvatarKey(profile, contextKey);
</script>

<section class="creator-profile" class:compact aria-label="平台作者资料">
  {#key imageKey}
    {@const renderedKey = imageKey}
    <div class="avatar">
      {#if avatarUrl && failedKey !== renderedKey}
        <img
          src={avatarUrl}
          alt=""
          width="44"
          height="44"
          loading="lazy"
          decoding="async"
          referrerpolicy="no-referrer"
          on:error={() => {
            if (creatorAvatarEventMatches(renderedKey, profile, contextKey)) failedKey = renderedKey;
          }}
        />
      {:else}
        <UserRound size={22} aria-hidden="true" />
      {/if}
    </div>
  {/key}
  <div class="profile-facts">
    <strong>平台昵称：{profile.nickname}</strong>
    <span>{previous ? '上次成功资料' : '资料观察时间'}：{formatDateLong(profile.observed_at)}</span>
    {#if failedKey === imageKey}
      <span>头像暂时无法显示；未回退到外站图片。</span>
    {:else if profile.avatar_state === 'retained'}
      <span>本次未更新头像，保留于 {formatDateLong(profile.avatar_observed_at)} 观察的旧头像。</span>
    {:else if profile.avatar_state === 'absent'}
      <span>没有可安全展示的头像。</span>
    {:else if !compact}
      <span>头像观察时间：{formatDateLong(profile.avatar_observed_at)}</span>
    {/if}
    {#if !compact}
      <a href={profile.profile_url} target="_blank" rel="noreferrer">查看平台主页</a>
    {/if}
  </div>
</section>

<style>
  .creator-profile {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    margin: 12px 0;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 12px;
    background: #fafbfd;
  }
  .avatar {
    display: flex;
    flex: 0 0 44px;
    width: 44px;
    height: 44px;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    overflow: hidden;
    background: var(--accent-soft);
    color: var(--text-muted);
  }
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .profile-facts {
    display: grid;
    gap: 3px;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  strong {
    color: var(--text);
    font-size: 12px;
  }
  span,
  a {
    color: var(--text-muted);
    font-size: 11px;
  }
  a {
    color: var(--accent);
  }
  .compact {
    border: 0;
    background: none;
    padding: 0;
    margin: 5px 0;
    gap: 8px;
  }
  .compact .avatar {
    flex-basis: 30px;
    width: 30px;
    height: 30px;
  }
  .compact strong,
  .compact span {
    font-size: 10px;
  }
</style>
