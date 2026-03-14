<script setup lang="ts">
const typeFilter = ref<string | null>(null)
const severityFilter = ref<string | null>(null)
const resolvedFilter = ref<boolean | null>(false)

const { issues, status, resolveIssue } = useIssues({
  type: typeFilter,
  severity: severityFilter,
  resolved: resolvedFilter,
})

const typeOptions = [
  { label: 'Tous', value: null },
  { label: 'Timeline', value: 'timeline_inconsistency' },
  { label: 'Personnage', value: 'character_contradiction' },
  { label: 'Info manquante', value: 'missing_info' },
  { label: 'Doublon suspect', value: 'duplicate_suspect' },
]

const severityOptions = [
  { label: 'Toutes', value: null },
  { label: 'Erreur', value: 'error' },
  { label: 'Avertissement', value: 'warning' },
]

const resolvedOptions = [
  { label: 'Non resolues', value: false },
  { label: 'Resolues', value: true },
  { label: 'Toutes', value: null },
]

const severityColor: Record<string, string> = {
  error: 'error',
  warning: 'warning',
}

async function toggleResolved(id: string, current: boolean) {
  await resolveIssue(id, !current)
}
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto">
    <div>
      <h1 class="text-2xl font-bold">
        Issues
      </h1>
      <p class="text-muted text-sm mt-1">
        Incoherences detectees dans les scenes importees
      </p>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-3">
      <USelect
        v-model="typeFilter"
        :items="typeOptions"
        value-key="value"
        placeholder="Type"
        class="w-48"
      />
      <USelect
        v-model="severityFilter"
        :items="severityOptions"
        value-key="value"
        placeholder="Severite"
        class="w-48"
      />
      <USelect
        v-model="resolvedFilter"
        :items="resolvedOptions"
        value-key="value"
        placeholder="Statut"
        class="w-48"
      />
    </div>

    <!-- Table -->
    <div v-if="status === 'pending'">
      <USkeleton class="h-60" />
    </div>
    <div v-else-if="issues?.length" class="space-y-3">
      <UCard v-for="issue in issues" :key="issue.id" :ui="{ body: 'p-4' }">
        <div class="flex items-start gap-3">
          <div class="flex-1 space-y-1">
            <div class="flex items-center gap-2">
              <UBadge
                :color="(severityColor[issue.severity] as any) || 'neutral'"
                variant="subtle"
                size="xs"
              >
                {{ issue.severity }}
              </UBadge>
              <UBadge color="neutral" variant="outline" size="xs">
                {{ issue.type }}
              </UBadge>
              <span v-if="issue.scene_id" class="text-xs text-muted">
                {{ issue.scene_id }}
              </span>
            </div>
            <p class="text-sm">
              {{ issue.description }}
            </p>
            <p v-if="issue.suggestion" class="text-xs text-muted italic">
              {{ issue.suggestion }}
            </p>
          </div>
          <UButton
            :icon="issue.resolved ? 'i-lucide-undo' : 'i-lucide-check'"
            :color="issue.resolved ? 'neutral' : 'success'"
            variant="ghost"
            size="xs"
            @click="toggleResolved(issue.id, issue.resolved)"
          >
            {{ issue.resolved ? 'Reouvrir' : 'Resoudre' }}
          </UButton>
        </div>
      </UCard>
    </div>
    <p v-else class="text-muted text-sm">
      Aucune issue trouvee
    </p>
  </div>
</template>
