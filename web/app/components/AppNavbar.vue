<script setup lang="ts">
const subtitles = [
  'Fiction\'s Encyclopedic Lore & Information eXpert',
  'Faithful Expert for Literary & eXpository details',
  'Film\'s Essential Lore & Intelligence eXchange',
]

const subtitle = subtitles[Math.floor(Math.random() * subtitles.length)]

const items = [[{
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
  icon: 'i-lucide-upload',
  to: '/import',
}, {
  label: 'Issues',
  icon: 'i-lucide-alert-triangle',
  to: '/issues',
}]]
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
