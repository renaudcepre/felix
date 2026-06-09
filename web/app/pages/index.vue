<script setup lang="ts">
// L'accueil, c'est le copilote. On redirige vers /chat (fiable en ssr:false).
await navigateTo('/chat', { replace: true })
</script>

<template>
  <div />
</template>
