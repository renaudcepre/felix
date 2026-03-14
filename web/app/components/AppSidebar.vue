<script setup lang="ts">
const subtitles = [
  'Fiction\'s Encyclopedic Lore & Information eXpert',
  'Faithful Expert for Literary & eXpository details',
  'Film\'s Essential Lore & Intelligence eXchange',
]

const subtitle = subtitles[Math.floor(Math.random() * subtitles.length)]

const items = [
  [{
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
  }],
]
</script>

<template>
  <UDashboardSidebar>
    <template #header>
      <div class="flex flex-col gap-1 p-2">
        <h1 class="text-xl font-bold text-felix-400">
          FELIX
        </h1>
        <p class="text-xs text-muted truncate">
          {{ subtitle }}
        </p>
      </div>
    </template>

    <UNavigationMenu :items="items" />

    <template #footer>
      <div class="p-3 text-xs text-muted">
        <p>Screenplay Assistant</p>
        <p class="text-dimmed">
          100% local
        </p>
      </div>
    </template>
  </UDashboardSidebar>
</template>
