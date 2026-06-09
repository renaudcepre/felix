<script setup lang="ts">
definePageMeta({ layout: false })

const route = useRoute()
const id = route.params.id as string

const { entity, status } = useEntity(id)

useHead({ title: () => `Felix — ${entity.value?.name ?? 'Entité'}` })

// props est un dict libre → on l'affiche tel quel, ordonné par clé.
const propEntries = computed(() =>
  Object.entries(entity.value?.props ?? {}).sort(([a], [b]) => a.localeCompare(b)),
)

const initial = computed(() => (entity.value?.name?.[0] ?? '?').toUpperCase())
</script>

<template>
  <div class="felix-fiche">
    <header class="fbar">
      <div class="fbar-left">
        <NuxtLink class="back-link" to="/entities">
          <AtelierIcon name="back" :size="17" />Retour aux entités
        </NuxtLink>
      </div>
      <div class="fbar-brand">
        <span class="felix-mark"><AtelierIcon name="felix" :size="15" /></span>
        <span class="fbar-project">Rivière basse</span>
      </div>
    </header>

    <main class="fwrap">
      <div v-if="status === 'pending'" class="empty">Chargement…</div>

      <template v-else-if="entity">
        <!-- En-tête -->
        <div class="ent-head">
          <span class="mono-avatar" :style="{ width: '56px', height: '56px', fontSize: '24px' }">
            {{ initial }}
          </span>
          <div>
            <h1 class="ent-name">{{ entity.name }}</h1>
            <div class="ent-tags">
              <span v-if="entity.entity_type" class="badge cap">{{ entity.entity_type }}</span>
              <span class="ent-ref">#{{ entity.id }}</span>
            </div>
          </div>
        </div>

        <!-- Propriétés -->
        <section class="card">
          <h2 class="card-title">Propriétés</h2>
          <div v-if="propEntries.length" class="prop-grid">
            <div v-for="[key, value] in propEntries" :key="key" class="prop-row">
              <div class="prop-key">{{ key }}</div>
              <div class="prop-val">{{ value }}</div>
            </div>
          </div>
          <p v-else class="empty">Aucune propriété notée.</p>
        </section>

        <!-- Relations -->
        <section class="card">
          <h2 class="card-title">Relations</h2>
          <div v-if="entity.relations.length" class="rel-list">
            <NuxtLink
              v-for="(rel, i) in entity.relations"
              :key="i"
              class="rel-row"
              :to="`/entities/${rel.other.id}`"
            >
              <div class="rel-left">
                <span class="mono-avatar neutral" :style="{ width: '30px', height: '30px', fontSize: '13px' }">
                  {{ (rel.other.name?.[0] ?? '?').toUpperCase() }}
                </span>
                <span class="rel-name">{{ rel.other.name }}</span>
                <span v-if="rel.other.entity_type" class="rel-meta">{{ rel.other.entity_type }}</span>
              </div>
              <div class="rel-left">
                <span class="badge badge-rel">{{ rel.rel_type }}</span>
                <span class="rel-dir" :class="rel.direction === 'in' ? 'in' : ''">
                  <AtelierIcon name="arrow" :size="15" />
                </span>
              </div>
            </NuxtLink>
          </div>
          <p v-else class="empty">Aucune relation notée.</p>
        </section>

        <!-- Chronologie -->
        <section class="card">
          <h2 class="card-title">Chronologie</h2>
          <div v-if="entity.events.length" class="chrono-list">
            <div v-for="ev in entity.events" :key="ev.ordre" class="chrono-row">
              <span class="chrono-ord">#{{ ev.ordre }}</span>
              <span class="chrono-text">{{ ev.resume }}</span>
            </div>
          </div>
          <p v-else class="empty">Aucun événement.</p>
        </section>

        <p class="fiche-foot">
          Les fiches alimentent la mémoire de Felix. Il les met à jour au fil de vos échanges.
        </p>
      </template>

      <div v-else class="empty">
        Entité introuvable. <NuxtLink to="/entities">Retour aux entités</NuxtLink>
      </div>
    </main>
  </div>
</template>
