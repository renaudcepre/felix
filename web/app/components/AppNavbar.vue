<script setup lang="ts">
const { loading: importLoading } = useImport()

const subtitles = [
  'Fiction\'s Encyclopedic Lore & Information eXpert',
  'Faithful Expert for Literary & eXpository details',
  'Film\'s Essential Lore & Intelligence eXchange',
]

const subtitle = subtitles[Math.floor(Math.random() * subtitles.length)]

const items = computed(() => [[{
  label: 'Dashboard',
  icon: 'i-lucide-layout-dashboard',
  to: '/',
}, {
  label: 'Chat',
  icon: 'i-lucide-message-square',
  to: '/chat',
}, {
  label: 'Personnages',
  icon: 'i-lucide-users',
  to: '/characters',
}, {
  label: 'Timeline',
  icon: 'i-lucide-calendar',
  to: '/timeline',
}, {
  label: 'Import',
  icon: importLoading.value ? 'i-lucide-loader-circle' : 'i-lucide-upload',
  to: '/import',
}, {
  label: 'Issues',
  icon: 'i-lucide-alert-triangle',
  to: '/issues',
}]])
</script>

<template>
  <header class="border-b border-default bg-default">
    <div class="flex items-center gap-6 px-4 h-12">
      <div class="flex items-center gap-2 shrink-0">
        <h1 class="text-lg font-bold text-felix-400">
          FELIX
        </h1>
        <p class="text-xs text-muted truncate hidden sm:block">
          {{ subtitle }}
        </p>
      </div>

      <UNavigationMenu :items="items" orientation="horizontal" />
    </div>
  </header>
</template>

<style scoped>
:deep(.i-lucide-loader-circle) {
  animation: spin 1.5s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
