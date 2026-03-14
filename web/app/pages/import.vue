<script setup lang="ts">
import type { ImportEvent } from '~/types'

const { progress, loading, events, clarification, startImport, respondClarification, reset } = useImport()
const files = ref<File[]>([])
const enrichProfiles = ref(true)
const dragging = ref(false)
const fileInput = ref<HTMLInputElement>()
const eventLog = ref<HTMLElement>()

function onDrop(e: DragEvent) {
  dragging.value = false
  if (!e.dataTransfer?.files) return
  addFiles(Array.from(e.dataTransfer.files))
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files) return
  addFiles(Array.from(input.files))
  input.value = ''
}

function addFiles(newFiles: File[]) {
  const txtFiles = newFiles.filter(f => f.name.endsWith('.txt'))
  const existingNames = new Set(files.value.map(f => f.name))
  for (const f of txtFiles) {
    if (!existingNames.has(f.name)) {
      files.value.push(f)
    }
  }
}

function removeFile(index: number) {
  files.value.splice(index, 1)
}

function onSubmit() {
  if (files.value.length > 0) {
    startImport(files.value, enrichProfiles.value)
  }
}

const progressPercent = computed(() => {
  if (!progress.value || !progress.value.total_scenes) return 0
  return Math.round((progress.value.processed_scenes / progress.value.total_scenes) * 100)
})

const statusLabel: Record<string, string> = {
  pending: 'En attente',
  analyzing: 'Analyse LLM',
  resolving: 'Resolution des entites',
  loading: 'Chargement en base',
  checking: 'Verification de coherence',
  profiling: 'Enrichissement des profils',
  done: 'Termine',
  error: 'Erreur',
}

const statusColor: Record<string, string> = {
  pending: 'neutral',
  analyzing: 'info',
  resolving: 'info',
  loading: 'info',
  checking: 'warning',
  profiling: 'info',
  done: 'success',
  error: 'error',
}

function formatEvent(ev: ImportEvent): { icon: string, text: string, color: string } {
  switch (ev.event) {
    case 'scene_analyzed':
      return {
        icon: 'i-lucide-search',
        text: `Analyse : ${ev.title} (${ev.characters?.length ?? 0} personnages, lieu : ${ev.location})`,
        color: 'text-blue-500',
      }
    case 'entity_resolved':
      if (ev.action === 'created') {
        return { icon: 'i-lucide-plus', text: `Nouveau : ${ev.name}`, color: 'text-green-500' }
      }
      if (ev.action === 'linked') {
        return { icon: 'i-lucide-link', text: `Lie : ${ev.name} -> ${ev.linked_to}`, color: 'text-yellow-500' }
      }
      return { icon: 'i-lucide-help-circle', text: `Entite : ${ev.name}`, color: 'text-muted' }
    case 'scene_loaded':
      return { icon: 'i-lucide-check', text: `Charge : ${ev.scene_id}`, color: 'text-green-600' }
    case 'issue_found':
      return { icon: 'i-lucide-alert-triangle', text: `Issue : ${ev.description}`, color: 'text-orange-500' }
    case 'profiling_character':
      return { icon: 'i-lucide-user', text: `Profiling : ${ev.name}...`, color: 'text-blue-400' }
    case 'character_profiled':
      return { icon: 'i-lucide-user-check', text: `Profil enrichi : ${ev.name}`, color: 'text-green-500' }
    case 'done':
      return {
        icon: 'i-lucide-check-circle',
        text: `Termine — ${ev.total_issues ?? 0} issues, ${ev.new_characters?.length ?? 0} nouveaux personnages`,
        color: 'text-green-600',
      }
    case 'error':
      return { icon: 'i-lucide-x-circle', text: `Erreur : ${ev.message}`, color: 'text-red-500' }
    default:
      return { icon: 'i-lucide-info', text: JSON.stringify(ev), color: 'text-muted' }
  }
}

// Visible events (filter out status_change and clarification_needed)
const visibleEvents = computed(() =>
  events.value.filter(e => !['status_change', 'clarification_needed'].includes(e.event)),
)

// Auto-scroll event log
watch(events, () => {
  nextTick(() => {
    if (eventLog.value) {
      eventLog.value.scrollTop = eventLog.value.scrollHeight
    }
  })
}, { deep: true })
</script>

<template>
  <div class="p-6 space-y-8 max-w-4xl mx-auto">
    <div>
      <h1 class="text-2xl font-bold">
        Import de scenes
      </h1>
      <p class="text-muted text-sm mt-1">
        Glissez-deposez vos fichiers .txt ou utilisez le selecteur
      </p>
    </div>

    <!-- Drop zone -->
    <UCard v-if="!progress">
      <div class="space-y-4">
        <div
          class="relative border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer"
          :class="dragging ? 'border-primary bg-primary/5' : 'border-muted hover:border-primary/50'"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
          @click="fileInput?.click()"
        >
          <input
            ref="fileInput"
            type="file"
            accept=".txt"
            multiple
            class="hidden"
            @change="onFileSelect"
          >
          <UIcon name="i-lucide-upload" class="text-3xl text-muted mb-2" />
          <p class="text-sm">
            <span class="font-medium text-primary">Cliquez</span> ou glissez-deposez des fichiers .txt
          </p>
          <p class="text-xs text-muted mt-1">
            1 fichier = 1 scene
          </p>
        </div>

        <!-- File list -->
        <div v-if="files.length" class="space-y-2">
          <div class="flex items-center justify-between text-sm">
            <span class="font-medium">{{ files.length }} fichier{{ files.length > 1 ? 's' : '' }}</span>
            <UButton
              variant="ghost"
              color="error"
              size="xs"
              :disabled="loading"
              @click="files = []"
            >
              Tout retirer
            </UButton>
          </div>
          <div v-for="(file, i) in files" :key="file.name" class="flex items-center justify-between p-2 rounded bg-elevated text-sm">
            <div class="flex items-center gap-2 min-w-0">
              <UIcon name="i-lucide-file-text" class="text-muted shrink-0" />
              <span class="truncate">{{ file.name }}</span>
              <span class="text-xs text-muted shrink-0">{{ (file.size / 1024).toFixed(1) }} Ko</span>
            </div>
            <UButton
              icon="i-lucide-x"
              variant="ghost"
              color="neutral"
              size="xs"
              :disabled="loading"
              @click="removeFile(i)"
            />
          </div>
        </div>

        <!-- Options -->
        <div class="flex items-center gap-2">
          <UCheckbox v-model="enrichProfiles" :disabled="loading" />
          <span class="text-sm">Enrichir les profils personnages (LLM)</span>
        </div>

        <!-- Submit -->
        <UButton
          icon="i-lucide-play"
          :loading="loading"
          :disabled="!files.length || loading"
          block
          @click="onSubmit"
        >
          Lancer l'import
        </UButton>
      </div>
    </UCard>

    <!-- Progress -->
    <UCard v-if="progress">
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <span class="font-medium">Statut</span>
          <UBadge
            :color="(statusColor[progress.status] as any) || 'neutral'"
            variant="subtle"
          >
            {{ statusLabel[progress.status] || progress.status }}
          </UBadge>
        </div>

        <UProgress
          v-if="progress.total_scenes > 0"
          :model-value="progressPercent"
          :max="100"
        />

        <div v-if="progress.current_scene" class="text-sm text-muted">
          Scene en cours : {{ progress.current_scene }}
        </div>

        <div class="text-sm">
          {{ progress.processed_scenes }} / {{ progress.total_scenes }} scenes traitees
        </div>

        <div v-if="progress.error" class="text-sm text-red-500">
          {{ progress.error }}
        </div>

        <!-- Clarification card -->
        <div
          v-if="clarification"
          class="border border-yellow-400 bg-yellow-50 dark:bg-yellow-950/30 dark:border-yellow-600 rounded-lg p-4 space-y-3"
        >
          <div class="flex items-start gap-2">
            <UIcon name="i-lucide-help-circle" class="text-yellow-500 mt-0.5 shrink-0" />
            <div>
              <p class="font-medium text-sm">
                {{ clarification.question }}
              </p>
              <p class="text-xs text-muted mt-1">
                Score de similarite : {{ (clarification.score * 100).toFixed(0) }}% — Resolution automatique dans 30s
              </p>
            </div>
          </div>
          <div class="flex gap-2">
            <UButton
              size="sm"
              color="success"
              variant="soft"
              @click="respondClarification(clarification!.id, 'link')"
            >
              Oui, meme entite
            </UButton>
            <UButton
              size="sm"
              color="error"
              variant="soft"
              @click="respondClarification(clarification!.id, 'new')"
            >
              Non, nouvelle entite
            </UButton>
          </div>
        </div>

        <!-- Event log -->
        <div v-if="visibleEvents.length" class="border-t pt-4 space-y-2">
          <p class="font-medium text-sm">
            Journal d'import
          </p>
          <div
            ref="eventLog"
            class="max-h-64 overflow-y-auto space-y-1 text-sm font-mono"
          >
            <div
              v-for="(ev, i) in visibleEvents"
              :key="i"
              class="flex items-start gap-2 py-0.5"
            >
              <UIcon :name="formatEvent(ev).icon" :class="formatEvent(ev).color" class="shrink-0 mt-0.5" />
              <span>{{ formatEvent(ev).text }}</span>
            </div>
          </div>
        </div>

        <!-- Reset -->
        <UButton
          v-if="progress.status === 'done' || progress.status === 'error'"
          icon="i-lucide-rotate-ccw"
          variant="soft"
          block
          @click="reset(); files = []"
        >
          Nouvel import
        </UButton>

        <!-- Results -->
        <div v-if="progress.status === 'done'" class="space-y-3 border-t pt-4">
          <p class="font-medium">
            Resultats
          </p>
          <div class="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span class="text-muted">Issues detectees :</span>
              <span class="ml-1 font-medium">{{ progress.issues_found }}</span>
            </div>
            <div>
              <span class="text-muted">Scenes importees :</span>
              <span class="ml-1 font-medium">{{ progress.processed_scenes }}</span>
            </div>
          </div>
          <div v-if="progress.new_characters.length" class="text-sm">
            <span class="text-muted">Nouveaux personnages :</span>
            <span class="ml-1">{{ progress.new_characters.join(', ') }}</span>
          </div>
          <div v-if="progress.new_locations.length" class="text-sm">
            <span class="text-muted">Nouveaux lieux :</span>
            <span class="ml-1">{{ progress.new_locations.join(', ') }}</span>
          </div>
        </div>
      </div>
    </UCard>
  </div>
</template>
