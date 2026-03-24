<script setup lang="ts">
const { groups, status, createGroup } = useGroups()
const router = useRouter()

const showAdd = ref(false)
const newName = ref('')
const newEra = ref('')
const creating = ref(false)
const createError = ref('')

async function addGroup() {
  if (!newName.value.trim()) return
  creating.value = true
  createError.value = ''
  try {
    const created = await createGroup({
      name: newName.value.trim(),
      era: newEra.value.trim() || undefined,
    })
    showAdd.value = false
    newName.value = ''
    newEra.value = ''
    router.push(`/groups/${created.id}`)
  }
  catch (e: any) {
    createError.value = e?.data?.detail || 'Error creating group'
  }
  finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">
          Groups
        </h1>
        <p class="text-sm text-muted mt-1">
          {{ groups?.length ?? 0 }} group{{ (groups?.length ?? 0) > 1 ? 's' : '' }}
        </p>
      </div>
      <UButton
        icon="i-lucide-plus"
        color="primary"
        label="New Group"
        @click="showAdd = true"
      />
    </div>

    <UCard v-if="showAdd">
      <div class="space-y-3">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <UFormField label="Name">
            <UInput v-model="newName" placeholder="Group name" autofocus />
          </UFormField>
          <UFormField label="Era (optional)">
            <UInput v-model="newEra" placeholder="e.g. 1940s, 2060s" />
          </UFormField>
        </div>
        <p v-if="createError" class="text-sm text-error">
          {{ createError }}
        </p>
        <div class="flex gap-2 justify-end">
          <UButton variant="ghost" color="neutral" label="Cancel" @click="showAdd = false" />
          <UButton
            color="primary"
            label="Create"
            :loading="creating"
            :disabled="!newName.trim()"
            @click="addGroup"
          />
        </div>
      </div>
    </UCard>

    <div v-if="status === 'pending'" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <USkeleton v-for="i in 4" :key="i" class="h-20" />
    </div>
    <div v-else-if="groups?.length" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <GroupCard v-for="g in groups" :key="g.id" :group="g" />
    </div>
    <p v-else class="text-muted text-sm">
      No groups yet
    </p>
  </div>
</template>
