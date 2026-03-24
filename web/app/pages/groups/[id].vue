<script setup lang="ts">
import type { CharacterSummary } from '~/types'

const route = useRoute()
const id = route.params.id as string

const { group, status, addMember, removeMember } = useGroup(id)
const { characters } = useCharacters()

const adding = ref(false)
const selectedCharId = ref('')

const availableCharacters = computed<CharacterSummary[]>(() => {
  if (!characters.value || !group.value) return []
  const memberIds = new Set(group.value.members.map(m => m.id))
  return characters.value.filter(c => !memberIds.has(c.id))
})

async function handleAddMember() {
  if (!selectedCharId.value) return
  adding.value = true
  try {
    await addMember(selectedCharId.value)
    selectedCharId.value = ''
  }
  finally {
    adding.value = false
  }
}

async function handleRemoveMember(charId: string) {
  await removeMember(charId)
}
</script>

<template>
  <div class="p-6 max-w-4xl mx-auto space-y-6">
    <NuxtLink to="/groups" class="text-sm text-muted hover:underline flex items-center gap-1">
      <UIcon name="i-lucide-arrow-left" />
      Back
    </NuxtLink>

    <div v-if="status === 'pending'" class="space-y-4">
      <USkeleton class="h-10 w-48" />
      <USkeleton class="h-40" />
    </div>

    <template v-else-if="group">
      <UCard>
        <div class="flex items-center gap-4 mb-6">
          <UAvatar
            icon="i-lucide-users"
            size="xl"
            color="neutral"
          />
          <div>
            <h1 class="text-2xl font-bold">
              {{ group.name }}
            </h1>
            <UBadge v-if="group.era" variant="subtle" size="xs" color="info">
              {{ group.era }}
            </UBadge>
          </div>
        </div>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">
              Members ({{ group.members.length }})
            </h2>
          </div>
        </template>

        <div v-if="group.members.length" class="space-y-2">
          <div
            v-for="member in group.members"
            :key="member.id"
            class="flex items-center justify-between p-2 rounded hover:bg-elevated"
          >
            <NuxtLink :to="`/characters/${member.id}`" class="flex items-center gap-2 hover:underline">
              <UAvatar :text="member.name[0]" size="sm" color="primary" />
              <span>{{ member.name }}</span>
              <UBadge v-if="member.era" variant="subtle" size="xs" color="info">
                {{ member.era }}
              </UBadge>
            </NuxtLink>
            <UButton
              icon="i-lucide-x"
              variant="ghost"
              color="error"
              size="xs"
              @click="handleRemoveMember(member.id)"
            />
          </div>
        </div>
        <p v-else class="text-muted text-sm">
          No members yet
        </p>

        <template #footer>
          <div class="flex items-center gap-2">
            <USelect
              v-model="selectedCharId"
              :items="availableCharacters.map(c => ({ label: c.name, value: c.id }))"
              value-key="value"
              placeholder="Select a character..."
              class="flex-1"
            />
            <UButton
              icon="i-lucide-plus"
              label="Add"
              color="primary"
              :loading="adding"
              :disabled="!selectedCharId"
              @click="handleAddMember"
            />
          </div>
        </template>
      </UCard>
    </template>

    <p v-else class="text-muted">
      Group not found
    </p>
  </div>
</template>
