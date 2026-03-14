<script setup lang="ts">
const { loading: importLoading } = useImport()

const subtitles = [
  'Fiction\'s Encyclopedic Lore & Information eXpert',
  'Faithful Expert for Literary & eXpository details',
  'Film\'s Essential Lore & Intelligence eXchange',
]

const subtitle = subtitles[Math.floor(Math.random() * subtitles.length)]

function isUpperCase(char: string) {
  return char !== ' ' && char === char.toUpperCase() && char !== char.toLowerCase()
}

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
  label: 'Lieux',
  icon: 'i-lucide-map-pin',
  to: '/locations',
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
        <h1 class="text-lg font-bold font-neuropol">
          <span class="felix-holo">F</span><span class="felix-holo">E</span><span class="felix-holo">L</span><span class="felix-holo">I</span><span class="felix-holo">X</span>
        </h1>
        <p class="text-xs text-muted truncate hidden sm:block font-mono">
          <template v-for="(char, i) in subtitle" :key="i">
            <span v-if="isUpperCase(char)" class="felix-holo font-semibold">{{ char }}</span>
            <template v-else>{{ char }}</template>
          </template>
        </p>
      </div>

      <UNavigationMenu :items="items" orientation="horizontal" />
    </div>
  </header>
</template>

<style scoped>
.felix-holo {
  display: inline-block;
  background: linear-gradient(
    135deg,
    #0db9f2 0%,
    #75e0ff 15%,
    #e879f9 30%,
    #0db9f2 45%,
    #34d399 60%,
    #75e0ff 75%,
    #e879f9 90%,
    #0db9f2 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: holo-shift 4s ease infinite;
}

.felix-holo:nth-child(2) { animation-delay: -0.6s; }
.felix-holo:nth-child(3) { animation-delay: -1.2s; }
.felix-holo:nth-child(4) { animation-delay: -1.8s; }
.felix-holo:nth-child(5) { animation-delay: -2.4s; }

@keyframes holo-shift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

:deep(.i-lucide-loader-circle) {
  animation: spin 1.5s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
