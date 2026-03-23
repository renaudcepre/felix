export default defineNuxtConfig({
  future: { compatibilityVersion: 4 },
  modules: ['@nuxt/ui', '@nuxt/eslint', '@nuxt/fonts'],
  ssr: false,
  devtools: { enabled: true },

  devServer: {
    port: 3007,
  },

  nitro: {
    devProxy: {
      '/api': {
        target: 'http://localhost:8000/api',
        changeOrigin: true,
      },
    },
  },

  app: {
    head: {
      htmlAttrs: { lang: 'fr' },
      title: 'Felix — Screenplay Assistant',
    },
  },

  runtimeConfig: {
    public: {
      apiStreamBase: 'http://localhost:8000',
    },
  },

  css: ['~/assets/css/main.css'],
  compatibilityDate: '2025-01-01',
})
