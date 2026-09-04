<script lang="ts">
  export let title: string;
  export let description: string;
</script>

<header class="page-heading">
  <div>
    <h1>{title}</h1>
    <p>{description}</p>
  </div>
  <div class="page-actions">
    <slot name="actions" />
  </div>
</header>
