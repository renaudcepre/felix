<script setup lang="ts">
// Jeu d'icônes inline (porté de felix-ui.jsx). Trait = currentColor.
const props = withDefaults(
  defineProps<{ name: string, size?: number, stroke?: number }>(),
  { size: 18, stroke: 1.6 },
)

interface IconDef { paths: string[], filled?: boolean, stroke?: number }

// Repli typé non-optionnel : sert de défaut au computed (sinon l'accès indexé
// rend IconDef | undefined sous noUncheckedIndexedAccess).
const FALLBACK: IconDef = { paths: ['M12 12h.01'], stroke: 3 }

const ICONS: Record<string, IconDef> = {
  send: { paths: ['M12 19V5 M6 11l6-6 6 6'] },
  felix: { paths: ['M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z'] },
  verify: { paths: ['M12 3l7 3v5c0 4.2-2.8 7.6-7 9-4.2-1.4-7-4.8-7-9V6z', 'M9 11.5l2 2 4-4.5'] },
  alert: { paths: ['M10.3 3.8 1.9 18a1.9 1.9 0 0 0 1.7 2.9h16.8A1.9 1.9 0 0 0 22 18L13.7 3.8a1.9 1.9 0 0 0-3.4 0z', 'M12 9v4', 'M12 17h.01'] },
  quote: { paths: ['M7 7H4v6h5V9 M17 7h-3v6h5V9'], filled: true },
  fiche: { paths: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M14 3v5h5', 'M9 13h4', 'M9 17h6'] },
  plus: { paths: ['M12 5v14 M5 12h14'] },
  back: { paths: ['M15 18l-6-6 6-6'] },
  arrow: { paths: ['M5 12h14 M13 6l6 6-6 6'] },
  close: { paths: ['M6 6l12 12 M18 6 6 18'] },
  check: { paths: ['M5 12.5l4.5 4.5L19 7'] },
  pencil: { paths: ['M12 20h9', 'M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z'] },
  trash: { paths: ['M3 6h18', 'M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2', 'M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6', 'M10 11v6', 'M14 11v6'] },
  people: { paths: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8', 'M22 21v-2a4 4 0 0 0-3-3.9', 'M16 3.1A4 4 0 0 1 16 11'] },
  dot: FALLBACK,
}

const icon = computed<IconDef>(() => ICONS[props.name] ?? FALLBACK)
const fill = computed(() => (icon.value.filled ? 'currentColor' : 'none'))
const strokeColor = computed(() => (icon.value.filled ? 'none' : 'currentColor'))
const strokeWidth = computed(() => icon.value.stroke ?? props.stroke)
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    :fill="fill"
    :stroke="strokeColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path v-for="(d, i) in icon.paths" :key="i" :d="d" />
  </svg>
</template>
