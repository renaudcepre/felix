<script setup lang="ts">
const route = useRoute()
const id = route.params.id as string

const { entity, status } = useEntity(id)

useHead({ title: () => `Felix — ${entity.value?.name ?? 'Entité'}` })

// props est un dict libre → on l'affiche tel quel, ordonné par clé.
const propEntries = computed(() =>
  Object.entries(entity.value?.props ?? {}).sort(([a], [b]) => a.localeCompare(b)),
)
</script>

<template>
  <div class="p-6 max-w-3xl mx-auto space-y-8">
    <div v-if="status === 'pending'" class="space-y-4">
      <USkeleton class="h-10 w-1/2" />
      <USkeleton class="h-40" />
    </div>

    <template v-else-if="entity">
      <!-- En-tête -->
      <div class="flex items-center gap-4">
        <UAvatar :text="(entity.name?.[0] ?? '?').toUpperCase()" size="xl" color="primary" />
        <div>
          <h1 class="text-2xl font-bold">
            {{ entity.name }}
          </h1>
          <UBadge v-if="entity.entity_type" color="info" variant="subtle" size="sm" class="mt-1">
            {{ entity.entity_type }}
          </UBadge>
        </div>
      </div>

      <!-- Propriétés -->
      <section>
        <h2 class="text-lg font-semibold mb-3">
          Propriétés
        </h2>
        <UCard v-if="propEntries.length" class="tape-effect" :ui="{ body: 'p-4' }">
          <dl class="grid grid-cols-1 sm:grid-cols-[10rem_1fr] gap-x-4 gap-y-2 text-sm">
            <template v-for="[key, value] in propEntries" :key="key">
              <dt class="font-medium text-muted capitalize">
                {{ key }}
              </dt>
              <dd class="whitespace-pre-wrap break-words">
                {{ value }}
              </dd>
            </template>
          </dl>
        </UCard>
        <p v-else class="text-muted text-sm">
          Aucune propriété.
        </p>
      </section>

      <!-- Relations -->
      <section>
        <h2 class="text-lg font-semibold mb-3">
          Relations
        </h2>
        <div v-if="entity.relations.length" class="space-y-2">
          <NuxtLink
            v-for="(rel, i) in entity.relations"
            :key="i"
            :to="`/entities/${rel.other.id}`"
            class="flex items-center gap-3 p-3 rounded border border-default hover:bg-elevated transition-colors"
          >
            <UIcon
              :name="rel.direction === 'out' ? 'i-lucide-arrow-right' : 'i-lucide-arrow-left'"
              class="text-felix-400 shrink-0"
            />
            <UBadge color="neutral" variant="subtle" size="xs">
              {{ rel.rel_type }}
            </UBadge>
            <span class="font-medium truncate">{{ rel.other.name }}</span>
            <span v-if="rel.other.entity_type" class="text-xs text-muted">
              {{ rel.other.entity_type }}
            </span>
          </NuxtLink>
        </div>
        <p v-else class="text-muted text-sm">
          Aucune relation.
        </p>
      </section>

      <!-- Chronologie -->
      <section>
        <h2 class="text-lg font-semibold mb-3">
          Chronologie
        </h2>
        <ol v-if="entity.events.length" class="space-y-2">
          <li
            v-for="ev in entity.events"
            :key="ev.ordre"
            class="flex gap-3 p-3 rounded border border-default"
          >
            <span class="font-mono text-xs text-felix-400 shrink-0 mt-0.5">#{{ ev.ordre }}</span>
            <span class="text-sm">{{ ev.resume }}</span>
          </li>
        </ol>
        <p v-else class="text-muted text-sm">
          Aucun événement.
        </p>
      </section>
    </template>

    <div v-else class="text-center py-12">
      <p class="text-muted">
        Entité introuvable.
      </p>
      <UButton to="/entities" variant="link" class="mt-2">
        Retour aux entités
      </UButton>
    </div>
  </div>
</template>
