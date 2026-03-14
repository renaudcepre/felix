// @ts-check
import withNuxt from './.nuxt/eslint.config.mjs'

export default withNuxt({
  files: ['app/components/ChatMessage.vue'],
  rules: { 'vue/no-v-html': 'off' },
})
