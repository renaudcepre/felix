<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string
const { character, status } = useCharacter(id)
</script>

<template>
  <div class="p-6 max-w-4xl mx-auto space-y-6">
    <UButton
      to="/characters"
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

    <template v-else-if="character">
      <UCard class="tape-effect">
        <div class="space-y-6">
          <!-- Header -->
          <div class="flex items-center gap-4">
            <UAvatar
              :text="character.name[0]"
              size="xl"
              color="primary"
            />
            <div>
              <h1 class="text-2xl font-bold">
                {{ character.name }}
              </h1>
              <div class="flex gap-2 mt-1">
                <UBadge
                  :color="character.era.includes('1940') ? 'warning' : 'info'"
                  variant="subtle"
                >
                  {{ character.era }}
                </UBadge>
                <UBadge v-if="character.status" variant="subtle" color="neutral">
                  {{ character.status }}
                </UBadge>
              </div>
              <p v-if="character.aliases.length" class="text-sm text-muted mt-1">
                Alias : {{ character.aliases.join(', ') }}
              </p>
            </div>
          </div>

          <!-- Details grid -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div v-if="character.age">
              <p class="text-xs font-semibold text-muted uppercase tracking-wide">
                Age
              </p>
              <p class="mt-1">
                {{ character.age }}
              </p>
            </div>
            <div v-if="character.physical">
              <p class="text-xs font-semibold text-muted uppercase tracking-wide">
                Physique
              </p>
              <p class="mt-1">
                {{ character.physical }}
              </p>
            </div>
            <div v-if="character.background" class="md:col-span-2">
              <p class="text-xs font-semibold text-muted uppercase tracking-wide">
                Background
              </p>
              <p class="mt-1 whitespace-pre-wrap">
                {{ character.background }}
              </p>
            </div>
            <div v-if="character.arc" class="md:col-span-2">
              <p class="text-xs font-semibold text-muted uppercase tracking-wide">
                Arc
              </p>
              <p class="mt-1 whitespace-pre-wrap">
                {{ character.arc }}
              </p>
            </div>
            <div v-if="character.traits">
              <p class="text-xs font-semibold text-muted uppercase tracking-wide">
                Traits
              </p>
              <p class="mt-1">
                {{ character.traits }}
              </p>
            </div>
          </div>
        </div>
      </UCard>

      <!-- Relations -->
      <UCard v-if="character.relations.length">
        <template #header>
          <h2 class="font-semibold">
            Relations
          </h2>
        </template>
        <div class="space-y-3">
          <div
            v-for="(rel, i) in character.relations"
            :key="i"
            class="flex items-center justify-between gap-2 py-2 border-b border-default last:border-0"
          >
            <div>
              <span class="font-medium">{{ rel.other_name }}</span>
              <UBadge variant="subtle" size="xs" class="ml-2" color="primary">
                {{ rel.relation_type }}
              </UBadge>
            </div>
            <div class="text-sm text-muted text-right">
              <span v-if="rel.era">{{ rel.era }}</span>
              <p v-if="rel.description" class="text-xs">
                {{ rel.description }}
              </p>
            </div>
          </div>
        </div>
      </UCard>
    </template>

    <p v-else class="text-muted">
      Personnage introuvable
    </p>
  </div>
</template>
