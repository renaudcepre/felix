export default defineNuxtConfig({
  future: { compatibilityVersion: 4 },
  modules: ['@nuxt/ui', '@nuxt/eslint', '@nuxt/fonts'],
  ssr: false,

  // Polices de l'atelier (thème papier).
  fonts: {
    families: [
      { name: 'Newsreader', provider: 'google' },
      { name: 'Hanken Grotesk', provider: 'google' },
      { name: 'IBM Plex Mono', provider: 'google' },
    ],
  },
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
