<script setup lang="ts">
defineProps<{
  role: 'user' | 'felix'
  content: string
}>()
</script>

<template>
  <div
    class="flex gap-3 max-w-3xl"
    :class="role === 'user' ? 'ml-auto flex-row-reverse' : ''"
  >
    <UAvatar
      :icon="role === 'user' ? 'i-lucide-user' : 'i-lucide-bot'"
      :color="role === 'user' ? 'success' : 'primary'"
      size="sm"
      class="shrink-0 mt-1"
    />
    <div
      class="rounded-lg px-4 py-3 text-sm whitespace-pre-wrap"
      :class="role === 'user'
        ? 'bg-green-100 text-green-900 dark:bg-green-900/30 dark:text-green-100'
        : 'bg-felix-100 text-felix-950 dark:bg-felix-950/50 dark:text-felix-100'"
    >
      {{ content }}
    </div>
  </div>
</template>
