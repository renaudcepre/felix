<script setup lang="ts">
const { messages, loading, sendMessage, clearChat } = useFelix()
const input = ref('')
const chatContainer = ref<HTMLElement>()

async function handleSend() {
  const text = input.value.trim()
  if (!text || loading.value) return

  input.value = ''
  await sendMessage(text)

  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-2rem)]">
    <!-- Header -->
    <div class="flex items-center justify-between p-4 border-b border-default">
      <div>
        <h1 class="text-lg font-bold">
          Chat avec Felix
        </h1>
        <p class="text-xs text-muted">
          Posez vos questions sur le scenario
        </p>
      </div>
      <UButton
        v-if="messages.length"
        icon="i-lucide-trash-2"
        variant="ghost"
        color="neutral"
        size="sm"
        @click="clearChat"
      />
    </div>

    <!-- Messages -->
    <div
      ref="chatContainer"
      class="flex-1 overflow-y-auto p-4 space-y-4"
    >
      <template v-if="messages.length">
        <ChatMessage
          v-for="(msg, i) in messages"
          :key="i"
          :role="msg.role"
          :content="msg.content"
        />
      </template>
      <div v-else class="flex items-center justify-center h-full">
        <div class="text-center text-muted">
          <UIcon name="i-lucide-message-square" class="text-4xl mb-2 text-felix-400" />
          <p class="text-sm">
            Commencez par poser une question
          </p>
          <p class="text-xs mt-1">
            Ex: "Qui est Marie ?" ou "Que se passe-t-il en mars 1942 ?"
          </p>
        </div>
      </div>

      <!-- Loading indicator -->
      <div v-if="loading" class="flex gap-3 max-w-3xl">
        <UAvatar
          icon="i-lucide-bot"
          color="primary"
          size="sm"
          class="shrink-0 mt-1"
        />
        <div class="bg-felix-100 dark:bg-felix-950/50 rounded-lg px-4 py-3">
          <div class="flex gap-1">
            <span class="w-2 h-2 rounded-full bg-felix-400 animate-bounce" />
            <span class="w-2 h-2 rounded-full bg-felix-400 animate-bounce [animation-delay:0.1s]" />
            <span class="w-2 h-2 rounded-full bg-felix-400 animate-bounce [animation-delay:0.2s]" />
          </div>
        </div>
      </div>
    </div>

    <!-- Input -->
    <div class="p-4 border-t border-default">
      <form class="flex gap-2" @submit.prevent="handleSend">
        <UInput
          v-model="input"
          placeholder="Posez une question a Felix..."
          class="flex-1"
          size="lg"
          :disabled="loading"
          autofocus
        />
        <UButton
          type="submit"
          icon="i-lucide-send"
          size="lg"
          :loading="loading"
        />
      </form>
    </div>
  </div>
</template>
