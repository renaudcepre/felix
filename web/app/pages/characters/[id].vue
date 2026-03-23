<script setup lang="ts">
import type { CharacterProfileUpdate, ConsistencyIssue, RelationUpsert } from '~/types'

const route = useRoute()
const id = route.params.id as string
const { character, status, updateCharacter, upsertRelation, deleteRelation, checkConsistency } = useCharacter(id)
const { characters: allCharacters } = useCharacters()

// --- Edit mode state ---
const editing = ref(false)
const saving = ref(false)
const editForm = ref<CharacterProfileUpdate>({})
const checking = ref(false)
const checkIssues = ref<ConsistencyIssue[]>([])
const checkDone = ref(false)

function startEditing() {
  if (!character.value) return
  editForm.value = {
    age: character.value.age,
    physical: character.value.physical,
    background: character.value.background,
    arc: character.value.arc,
    traits: character.value.traits,
  }
  editing.value = true
}

function resetCheck() {
  checkIssues.value = []
  checkDone.value = false
}

function cancelEditing() {
  editing.value = false
  editForm.value = {}
  resetCheck()
}

async function saveProfile() {
  if (!character.value) return
  const original = character.value
  const modified: CharacterProfileUpdate = {}
  const fields = ['age', 'physical', 'background', 'arc', 'traits'] as const
  for (const f of fields) {
    if (editForm.value[f] !== original[f]) {
      modified[f] = editForm.value[f] ?? null
    }
  }
  if (Object.keys(modified).length === 0) {
    editing.value = false
    return
  }
  saving.value = true
  try {
    await updateCharacter(modified)
    editing.value = false
    resetCheck()
  }
  finally {
    saving.value = false
  }
}

async function runCheck() {
  checking.value = true
  checkDone.value = false
  checkIssues.value = []
  try {
    checkIssues.value = await checkConsistency(editForm.value)
    checkDone.value = true
  }
  finally {
    checking.value = false
  }
}

// --- Relation management ---
const showAddRelation = ref(false)
const newRelation = ref<RelationUpsert>({ relation_type: '', description: null, era: null })
const selectedCharId = ref('')
const savingRelation = ref(false)

const otherCharacters = computed(() => {
  if (!allCharacters.value) return []
  return allCharacters.value
    .filter(c => c.id !== id)
    .map(c => ({ label: c.name, value: c.id }))
})

async function addRelation() {
  if (!selectedCharId.value || !newRelation.value.relation_type) return
  savingRelation.value = true
  try {
    await upsertRelation(selectedCharId.value, newRelation.value)
    showAddRelation.value = false
    newRelation.value = { relation_type: '', description: null, era: null }
    selectedCharId.value = ''
  }
  finally {
    savingRelation.value = false
  }
}

async function removeRelation(otherName: string, relationType: string) {
  // Trouver l'ID du personnage par son nom
  const other = allCharacters.value?.find(c => c.name === otherName)
  if (!other) return
  await deleteRelation(other.id, relationType)
}
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
          <div class="flex items-center justify-between">
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
            <UButton
              v-if="!editing"
              icon="i-lucide-pencil"
              variant="soft"
              color="primary"
              label="Modifier"
              @click="startEditing"
            />
          </div>

          <!-- View mode -->
          <div v-if="!editing" class="grid grid-cols-1 md:grid-cols-2 gap-4">
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

          <!-- Edit mode -->
          <div v-else class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <UFormField label="Age">
                <UInput v-model="editForm.age" placeholder="Age du personnage" />
              </UFormField>
              <UFormField label="Physique">
                <UInput v-model="editForm.physical" placeholder="Description physique" />
              </UFormField>
            </div>
            <UFormField label="Background">
              <UTextarea v-model="editForm.background" placeholder="Background" :rows="4" autoresize />
            </UFormField>
            <UFormField label="Arc">
              <UTextarea v-model="editForm.arc" placeholder="Arc narratif" :rows="4" autoresize />
            </UFormField>
            <UFormField label="Traits">
              <UInput v-model="editForm.traits" placeholder="Traits de caractere" />
            </UFormField>
            <!-- Consistency check results -->
            <div v-if="checkDone && checkIssues.length === 0" class="rounded-lg bg-green-50 dark:bg-green-950 p-3 text-sm text-green-700 dark:text-green-300">
              Aucune incohérence détectée.
            </div>
            <div v-if="checkIssues.length" class="space-y-2">
              <UAlert
                v-for="(issue, i) in checkIssues"
                :key="i"
                :color="issue.severity === 'error' ? 'error' : 'warning'"
                :title="issue.description"
                :description="issue.suggestion"
              />
            </div>

            <div class="flex gap-2 justify-end">
              <UButton variant="ghost" color="neutral" label="Annuler" @click="cancelEditing" />
              <UButton
                icon="i-lucide-shield-check"
                variant="soft"
                color="warning"
                label="Vérifier"
                :loading="checking"
                @click="runCheck"
              />
              <UButton color="primary" label="Enregistrer" :loading="saving" @click="saveProfile" />
            </div>
          </div>
        </div>
      </UCard>

      <!-- Relations -->
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h2 class="font-semibold">
              Relations
            </h2>
            <UButton
              v-if="!showAddRelation"
              icon="i-lucide-plus"
              variant="soft"
              size="xs"
              label="Ajouter"
              @click="showAddRelation = true"
            />
          </div>
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
            <div class="flex items-center gap-2">
              <div class="text-sm text-muted text-right">
                <span v-if="rel.era">{{ rel.era }}</span>
                <p v-if="rel.description" class="text-xs">
                  {{ rel.description }}
                </p>
              </div>
              <UButton
                icon="i-lucide-x"
                variant="ghost"
                color="error"
                size="xs"
                @click="removeRelation(rel.other_name, rel.relation_type)"
              />
            </div>
          </div>

          <p v-if="!character.relations.length && !showAddRelation" class="text-sm text-muted">
            Aucune relation
          </p>

          <!-- Add relation form -->
          <div v-if="showAddRelation" class="border border-default rounded-lg p-4 space-y-3">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <UFormField label="Personnage">
                <USelect
                  v-model="selectedCharId"
                  :items="otherCharacters"
                  placeholder="Choisir un personnage"
                />
              </UFormField>
              <UFormField label="Type de relation">
                <UInput v-model="newRelation.relation_type" placeholder="ex: frere, allie, rival" />
              </UFormField>
            </div>
            <UFormField label="Description">
              <UInput v-model="newRelation.description" placeholder="Description (optionnel)" />
            </UFormField>
            <div class="flex gap-2 justify-end">
              <UButton variant="ghost" color="neutral" label="Annuler" @click="showAddRelation = false" />
              <UButton
                color="primary"
                label="Ajouter"
                :loading="savingRelation"
                :disabled="!selectedCharId || !newRelation.relation_type"
                @click="addRelation"
              />
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
