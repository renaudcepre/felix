<script setup lang="ts">
const { characters, status: charStatus } = useCharacters()
const era = ref<string | null>(null)
const { events, status: timeStatus } = useTimeline(era)
const { scenes } = useScenes()
const { issues } = useIssues({ resolved: ref(false) })
</script>

<template>
  <div class="p-6 space-y-8 max-w-7xl mx-auto">
    <div>
      <h1 class="text-2xl font-bold">
        Dashboard
      </h1>
      <p class="text-muted text-sm mt-1">
        Vue d'ensemble du projet
      </p>
    </div>

    <!-- Stats -->
    <div class="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-4">
      <UCard class="tape-effect">
        <div class="text-center">
          <p class="text-3xl font-bold text-felix-400">
            {{ characters?.length ?? '...' }}
          </p>
          <p class="text-sm text-muted mt-1">
            Personnages
          </p>
        </div>
      </UCard>
      <UCard class="tape-effect">
        <div class="text-center">
          <p class="text-3xl font-bold text-felix-400">
            {{ events?.length ?? '...' }}
          </p>
          <p class="text-sm text-muted mt-1">
            Evenements
          </p>
        </div>
      </UCard>
      <UCard class="tape-effect">
        <div class="text-center">
          <p class="text-3xl font-bold text-felix-400">
            {{ characters && events ? (new Set([...(characters || []), ...(events || [])].map(e => 'era' in e ? e.era : ''))).size : '...' }}
          </p>
          <p class="text-sm text-muted mt-1">
            Epoques
          </p>
        </div>
      </UCard>
      <UCard class="tape-effect">
        <div class="text-center">
          <p class="text-3xl font-bold text-felix-400">
            {{ scenes?.length ?? '...' }}
          </p>
          <p class="text-sm text-muted mt-1">
            Scenes importees
          </p>
        </div>
      </UCard>
      <UCard class="tape-effect">
        <div class="text-center">
          <p class="text-3xl font-bold text-felix-400">
            {{ issues?.length ?? '...' }}
          </p>
          <p class="text-sm text-muted mt-1">
            Issues
          </p>
        </div>
      </UCard>
    </div>

    <!-- Characters grid -->
    <div>
      <h2 class="text-lg font-semibold mb-4">
        Personnages
      </h2>
      <div v-if="charStatus === 'pending'" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <USkeleton v-for="i in 4" :key="i" class="h-20" />
      </div>
      <div v-else-if="characters?.length" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <CharacterCard v-for="c in characters" :key="c.id" :character="c" />
      </div>
      <p v-else class="text-muted text-sm">
        Aucun personnage
      </p>
    </div>

    <!-- Recent timeline -->
    <div>
      <h2 class="text-lg font-semibold mb-4">
        Derniers evenements
      </h2>
      <div v-if="timeStatus === 'pending'">
        <USkeleton class="h-40" />
      </div>
      <div v-else-if="events?.length" class="space-y-2">
        <UCard v-for="evt in events.slice(0, 5)" :key="evt.id" :ui="{ body: 'p-3' }">
          <div class="flex items-center justify-between gap-2">
            <div class="min-w-0">
              <p class="font-medium truncate">
                {{ evt.title }}
              </p>
              <p class="text-xs text-muted">
                {{ evt.date }} — {{ evt.location || 'Lieu inconnu' }}
              </p>
            </div>
            <UBadge
              :color="evt.era.includes('1940') ? 'warning' : 'info'"
              variant="subtle"
              size="xs"
            >
              {{ evt.era }}
            </UBadge>
          </div>
        </UCard>
      </div>
      <p v-else class="text-muted text-sm">
        Aucun evenement
      </p>
    </div>
  </div>
</template>
