<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { location, status } = useLocation(id)
</script>

<template>
  <div class="p-6 max-w-4xl mx-auto space-y-6">
    <UButton
      to="/locations"
      icon="i-lucide-arrow-left"
      variant="ghost"
      color="neutral"
      size="sm"
      label="Retour"
    />

    <div v-if="status === 'pending'" class="space-y-4">
      <USkeleton class="h-12 w-64" />
      <USkeleton class="h-60" />
    </div>

    <template v-else-if="location">
      <UCard class="tape-effect">
        <div class="space-y-6">
          <!-- Header -->
          <div class="flex items-center gap-4">
            <UAvatar
              icon="i-lucide-map-pin"
              size="xl"
              color="primary"
            />
            <div>
              <h1 class="text-2xl font-bold">
                {{ location.name }}
              </h1>
              <div class="flex gap-2 mt-1">
                <UBadge
                  v-if="location.era"
                  :color="location.era.includes('1940') ? 'warning' : 'info'"
                  variant="subtle"
                >
                  {{ location.era }}
                </UBadge>
              </div>
            </div>
          </div>

          <!-- Details -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div v-if="location.description" class="md:col-span-2">
              <p class="text-xs font-semibold text-muted uppercase tracking-wide">
                Description
              </p>
              <p class="mt-1 whitespace-pre-wrap">
                {{ location.description }}
              </p>
            </div>
            <div v-if="location.address">
              <p class="text-xs font-semibold text-muted uppercase tracking-wide">
                Adresse
              </p>
              <p class="mt-1">
                {{ location.address }}
              </p>
            </div>
          </div>
        </div>
      </UCard>

      <!-- Scenes liees -->
      <UCard v-if="location.scenes.length">
        <template #header>
          <h2 class="font-semibold">
            Scenes ({{ location.scenes.length }})
          </h2>
        </template>
        <div class="space-y-3">
          <div
            v-for="scene in location.scenes"
            :key="scene.id"
            class="flex items-center justify-between gap-2 py-2 border-b border-default last:border-0"
          >
            <div>
              <span class="font-medium">{{ scene.title || scene.filename }}</span>
            </div>
            <div class="flex gap-2">
              <UBadge v-if="scene.era" variant="subtle" size="xs" color="info">
                {{ scene.era }}
              </UBadge>
              <span v-if="scene.date" class="text-sm text-muted">{{ scene.date }}</span>
            </div>
          </div>
        </div>
      </UCard>
    </template>

    <p v-else class="text-muted">
      Lieu introuvable
    </p>
  </div>
</template>
