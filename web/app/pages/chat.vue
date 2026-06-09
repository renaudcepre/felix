<script setup lang="ts">
import type { AtelierMsg, ChoiceOption, ResolveOption } from '~/types/atelier'

// Page autonome (pas le layout cyan de l'app de référence).
definePageMeta({ layout: false })
useHead({ title: 'Felix — Atelier · Rivière basse' })

// ───────── Chat câblé au backend (SSE /api/atelier/chat) ─────────
const { messages, typing, sendMessage } = useAtelier()

const draft = ref('')
const scrollRef = ref<HTMLElement | null>(null)
const taRef = ref<HTMLTextAreaElement | null>(null)

function patch(id: number, fn: (m: AtelierMsg) => AtelierMsg) {
  messages.value = messages.value.map(x => (x.id === id ? fn(x) : x))
}
function scrollToBottom() {
  nextTick(() => {
    const el = scrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}
watch([messages, typing], scrollToBottom, { deep: true })
onMounted(scrollToBottom)

function sendText(text: string) {
  const t = text.trim()
  if (!t) return
  draft.value = ''
  if (taRef.value) taRef.value.style.height = 'auto'
  void sendMessage(t)
}

// Le bot MVP n'émet pas encore de messages choice/cite/alert — l'UI les
// supporte (AtelierMessage), et ces handlers renvoient la décision de
// l'auteur au bot comme message texte en attendant le câblage dédié.
function pickChoice(msg: AtelierMsg, opt: ChoiceOption) {
  patch(msg.id, x => ({ ...x, answered: true, chosen: opt.k }))
  void sendMessage(opt.label)
}

function freeChoice(msg: AtelierMsg, text: string) {
  const t = text.trim()
  if (!t) return
  patch(msg.id, x => ({ ...x, answered: true, chosen: 'libre' }))
  void sendMessage(t)
}

function setAlertStatus(msg: AtelierMsg, status: string) {
  patch(msg.id, x => ({ ...x, status: status as AtelierMsg['status'] }))
}

function resolveAlert(msg: AtelierMsg, res: ResolveOption) {
  patch(msg.id, x => ({ ...x, status: 'resolved', resolution: res.label }))
  void sendMessage(res.label)
}

function grow(el: HTMLTextAreaElement) {
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 180)}px`
}
function onInput(e: Event) {
  const el = e.target as HTMLTextAreaElement
  draft.value = el.value
  grow(el)
}
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendText(draft.value)
  }
}
</script>

<template>
  <div class="felix-atelier">
    <header class="topbar">
      <div class="tb-left">
        <span class="felix-mark"><AtelierIcon name="felix" :size="18" /></span>
        <span class="felix-word">Felix</span>
        <span class="tb-sep" />
        <span class="tb-project">Rivière basse</span>
      </div>
      <div class="tb-right">
        <span class="tb-save"><span class="save-dot" />Enregistré</span>
        <NuxtLink class="btn btn-outline" to="/entities?type=personnage"><AtelierIcon name="people" :size="16" />Personnages</NuxtLink>
      </div>
    </header>

    <div ref="scrollRef" class="thread-wrap">
      <div class="thread">
        <div class="daymark"><span>Aujourd'hui</span></div>

        <AtelierMessage
          v-for="m in messages"
          :key="m.id"
          :msg="m"
          @pick="pickChoice"
          @free="freeChoice"
          @resolve="resolveAlert"
          @status="setAlertStatus"
        />

        <div v-if="typing" class="msg msg-felix">
          <div class="msg-av"><span class="mono-avatar">F</span></div>
          <div class="msg-main">
            <div class="typing"><span /><span /><span /></div>
          </div>
        </div>

        <div style="height: 8px" />
      </div>
    </div>

    <div class="composer-wrap">
      <div class="composer-col">
        <div class="composer">
          <textarea
            ref="taRef"
            class="composer-ta"
            rows="1"
            :value="draft"
            placeholder="Écris à Felix… (idée, scène, question)"
            @input="onInput"
            @keydown="onKeydown"
          />
          <button class="composer-send" :disabled="!draft.trim()" title="Envoyer" @click="sendText(draft)">
            <AtelierIcon name="send" :size="18" />
          </button>
        </div>
        <div class="composer-hint">Felix peut modifier les fiches et signaler les incohérences du scénario.</div>
      </div>
    </div>
  </div>
</template>

<style>
/* ============================================================
   FELIX — atelier d'écriture. Tout est scopé sous .felix-atelier
   (tokens en valeurs littérales → indépendant du thème cyan).
   ============================================================ */
.felix-atelier {
  --paper: #f3ede1;
  --paper-2: #ece3d2;
  --card: #fbf8f1;
  --card-2: #f7f1e6;
  --ink: #2a251e;
  --ink-2: #6b6052;
  --ink-3: #9a8e7b;
  --line: #e2d8c4;
  --line-2: #d6c9b0;
  --gold: #a9772a;
  --gold-deep: #8a5f1f;
  --gold-soft: #f0e3c8;
  --gold-line: #e3cd9b;
  --terra: #b14a30;
  --terra-soft: #f4ddd1;
  --terra-line: #e6bda9;
  --sage: #5e7355;
  --sage-soft: #e2e8da;
  --sage-line: #c5d2b8;
  --serif: 'Newsreader', Georgia, 'Times New Roman', serif;
  --sans: 'Hanken Grotesk', system-ui, -apple-system, sans-serif;
  --mono: 'IBM Plex Mono', 'SFMono-Regular', Menlo, monospace;
  --r-sm: 7px;
  --r-md: 11px;
  --r-lg: 16px;
  --shadow-sm: 0 1px 2px rgba(54, 42, 20, .06), 0 1px 1px rgba(54, 42, 20, .04);
  --shadow-md: 0 2px 8px rgba(54, 42, 20, .07), 0 8px 24px rgba(54, 42, 20, .06);
  --shadow-lg: 0 6px 18px rgba(54, 42, 20, .10), 0 18px 50px rgba(54, 42, 20, .10);

  height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* Grain papier (overlay subtil) */
.felix-atelier::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 9999;
  opacity: .035;
  mix-blend-mode: multiply;
  background-image: radial-gradient(circle at 50% 50%, #000 .6px, transparent .7px);
  background-size: 3px 3px;
}

.felix-atelier ::selection { background: var(--gold-soft); color: var(--ink); }
.felix-atelier button { font-family: inherit; cursor: pointer; }
.felix-atelier a { color: inherit; text-decoration: none; }

/* Scrollbar douce */
.felix-atelier *::-webkit-scrollbar { width: 11px; height: 11px; }
.felix-atelier *::-webkit-scrollbar-thumb { background: #d9cdb4; border-radius: 100px; border: 3px solid var(--paper); }
.felix-atelier *::-webkit-scrollbar-thumb:hover { background: #cbbd9d; }
.felix-atelier *::-webkit-scrollbar-track { background: transparent; }

/* Boutons */
.felix-atelier .btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: var(--sans);
  font-weight: 600;
  font-size: 14px;
  line-height: 1;
  white-space: nowrap;
  padding: 10px 16px;
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: transparent;
  color: var(--ink);
  transition: background .15s ease, border-color .15s ease, transform .06s ease, color .15s ease;
}
.felix-atelier .btn:active { transform: translateY(1px); }
.felix-atelier .btn svg { width: 16px; height: 16px; }
.felix-atelier .btn-outline { border-color: var(--line-2); background: var(--card); color: var(--ink); }
.felix-atelier .btn-outline:hover { border-color: var(--gold-line); background: var(--gold-soft); }
.felix-atelier .btn-ghost { color: var(--ink-2); }
.felix-atelier .btn-ghost:hover { background: var(--card-2); color: var(--ink); }

/* Monogramme */
.felix-atelier .mono-avatar {
  display: grid;
  place-items: center;
  flex: none;
  width: 32px;
  height: 32px;
  font-size: 13px;
  border-radius: 50%;
  background: var(--gold-soft);
  border: 1px solid var(--gold-line);
  color: var(--gold-deep);
  font-family: var(--serif);
  font-weight: 600;
}

/* Barre du haut */
.felix-atelier .topbar {
  height: 60px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 22px;
  border-bottom: 1px solid var(--line);
  background: rgba(243, 237, 225, .82);
  backdrop-filter: blur(10px);
  position: sticky;
  top: 0;
  z-index: 5;
}
.felix-atelier .tb-left { display: flex; align-items: center; gap: 12px; }
.felix-atelier .tb-right { display: flex; align-items: center; gap: 14px; }
.felix-atelier .felix-mark { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 8px; background: var(--gold); color: #fdfaf2; }
.felix-atelier .felix-word { font-family: var(--serif); font-weight: 600; font-size: 19px; margin-left: 1px; letter-spacing: .01em; }
.felix-atelier .tb-sep { width: 4px; height: 4px; border-radius: 50%; background: var(--line-2); }
.felix-atelier .tb-project { font-family: var(--sans); font-weight: 600; font-size: 14px; color: var(--ink-2); }
.felix-atelier .tb-save { display: flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--ink-3); }
.felix-atelier .save-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--sage); box-shadow: 0 0 0 3px var(--sage-soft); }

/* Fil */
.felix-atelier .thread-wrap { flex: 1; overflow-y: auto; }
.felix-atelier .thread { max-width: 768px; margin: 0 auto; padding: 26px 24px 14px; }
.felix-atelier .daymark { display: flex; align-items: center; gap: 14px; margin: 2px 2px 26px; }
.felix-atelier .daymark::before, .felix-atelier .daymark::after { content: ""; height: 1px; flex: 1; background: var(--line); }
.felix-atelier .daymark span { font-family: var(--mono); font-size: 10.5px; letter-spacing: .12em; text-transform: uppercase; color: var(--ink-3); }

.felix-atelier .msg { display: flex; gap: 13px; margin-bottom: 22px; animation: felix-rise .34s cubic-bezier(.2, .7, .3, 1) both; }
.felix-atelier .msg-user { justify-content: flex-end; }
.felix-atelier .msg-av { flex: none; margin-top: 1px; }
.felix-atelier .msg-main { min-width: 0; flex: 1; }
@keyframes felix-rise { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: none; } }

.felix-atelier .felix-text { font-family: var(--serif); font-size: 17px; line-height: 1.68; color: var(--ink); margin: 4px 0; max-width: 62ch; text-wrap: pretty; }
.felix-atelier .felix-text > :first-child { margin-top: 0; }
.felix-atelier .felix-text > :last-child { margin-bottom: 0; }
.felix-atelier .felix-text p { margin: 0 0 8px; }
.felix-atelier .felix-text strong { font-weight: 650; color: var(--ink); }
.felix-atelier .felix-text em { font-style: italic; color: var(--gold-deep); }
.felix-atelier .felix-text ul,
.felix-atelier .felix-text ol { margin: 6px 0 8px; padding-left: 1.35em; }
.felix-atelier .felix-text li { margin: 2px 0; padding-left: 2px; }
.felix-atelier .felix-text li::marker { color: var(--gold); }
.felix-atelier .felix-text a { color: var(--gold-deep); text-decoration: underline; text-underline-offset: 2px; }
.felix-atelier .felix-text code { font-family: var(--mono); font-size: 0.88em; background: var(--gold-soft); padding: 0.05em 0.35em; border-radius: 4px; }
.felix-atelier .felix-text blockquote { margin: 6px 0; padding-left: 12px; border-left: 2px solid var(--gold-line); color: var(--ink-2); font-style: italic; }

.felix-atelier .bubble {
  font-family: var(--serif);
  font-size: 16.5px;
  line-height: 1.6;
  color: var(--ink);
  background: #fffdf8;
  border: 1px solid var(--line-2);
  border-radius: 15px 15px 5px 15px;
  padding: 11px 16px;
  max-width: 74%;
  box-shadow: var(--shadow-sm);
  text-wrap: pretty;
}

.felix-atelier .typing { display: inline-flex; gap: 5px; padding: 13px 2px; }
.felix-atelier .typing span { width: 7px; height: 7px; border-radius: 50%; background: var(--ink-3); animation: felix-bob 1.2s infinite ease-in-out; }
.felix-atelier .typing span:nth-child(2) { animation-delay: .15s; }
.felix-atelier .typing span:nth-child(3) { animation-delay: .3s; }
@keyframes felix-bob { 0%, 80%, 100% { opacity: .3; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-4px); } }

/* Tool use */
.felix-atelier .tool-card { max-width: 560px; border: 1px solid var(--gold-line); background: #fbf6ea; border-radius: var(--r-md); overflow: hidden; box-shadow: var(--shadow-sm); margin: 3px 0; }
.felix-atelier .tool-head { display: flex; align-items: center; gap: 9px; padding: 8px 12px; background: var(--gold-soft); border-bottom: 1px solid var(--gold-line); }
.felix-atelier .tool-ic { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 6px; background: var(--gold); color: #fdfaf2; }
.felix-atelier .tool-label { font-family: var(--mono); font-size: 11px; letter-spacing: .05em; text-transform: uppercase; color: var(--gold-deep); }
.felix-atelier .tool-spacer { flex: 1; }
.felix-atelier .tool-link { display: inline-flex; align-items: center; gap: 5px; font-family: var(--sans); font-size: 12.5px; font-weight: 600; color: var(--gold-deep); }
.felix-atelier .tool-link:hover { text-decoration: underline; }
.felix-atelier .tool-body { padding: 12px 14px; }
.felix-atelier .tool-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 9px; }
.felix-atelier .tool-subj { font-family: var(--sans); font-weight: 700; font-size: 14px; color: var(--ink); }
.felix-atelier .tool-fdot { width: 3px; height: 3px; border-radius: 50%; background: var(--line-2); }
.felix-atelier .tool-field { font-family: var(--mono); font-size: 12px; color: var(--ink-2); }
.felix-atelier .tool-added { display: flex; gap: 10px; padding: 9px 11px; background: #fff; border: 1px solid var(--line); border-left: 3px solid var(--gold); border-radius: 6px; }
.felix-atelier .tool-plus { font-family: var(--mono); font-size: 11px; color: var(--sage); flex: none; margin-top: 2px; }
.felix-atelier .tool-text { font-family: var(--serif); font-size: 15px; line-height: 1.5; color: var(--ink); }

/* Choix multiple */
.felix-atelier .choice-card { max-width: 580px; border: 1px solid var(--line-2); background: var(--card); border-radius: var(--r-md); padding: 16px; box-shadow: var(--shadow-sm); }
.felix-atelier .choice-q { font-family: var(--serif); font-size: 16.5px; font-weight: 500; line-height: 1.5; color: var(--ink); margin-bottom: 13px; text-wrap: pretty; }
.felix-atelier .choice-opts { display: flex; flex-direction: column; gap: 8px; }
.felix-atelier .choice-opt { display: flex; gap: 12px; align-items: flex-start; text-align: left; padding: 11px 13px; border: 1px solid var(--line-2); background: #fffdf8; border-radius: 8px; transition: border-color .14s ease, background .14s ease, transform .14s ease, opacity .14s ease; }
.felix-atelier .choice-opt:hover:not(:disabled) { border-color: var(--gold); background: var(--gold-soft); transform: translateX(2px); }
.felix-atelier .opt-k { flex: none; width: 24px; height: 24px; border-radius: 6px; display: grid; place-items: center; font-family: var(--mono); font-weight: 600; font-size: 13px; background: var(--card-2); border: 1px solid var(--line-2); color: var(--ink-2); }
.felix-atelier .choice-opt:hover:not(:disabled) .opt-k { background: var(--gold); color: #fff; border-color: var(--gold); }
.felix-atelier .opt-main { display: flex; flex-direction: column; gap: 2px; }
.felix-atelier .opt-label { font-family: var(--sans); font-weight: 600; font-size: 14px; color: var(--ink); }
.felix-atelier .opt-desc { font-family: var(--serif); font-size: 14px; line-height: 1.45; color: var(--ink-2); text-wrap: pretty; }
.felix-atelier .choice-opt.chosen { border-color: var(--sage); background: var(--sage-soft); }
.felix-atelier .choice-opt.chosen .opt-k { background: var(--sage); color: #fff; border-color: var(--sage); }
.felix-atelier .choice-opt.dim { opacity: .42; }
.felix-atelier .choice-opt:disabled { cursor: default; }
.felix-atelier .choice-free { margin-top: 14px; padding-top: 13px; border-top: 1px dashed var(--line-2); }
.felix-atelier .free-or { font-family: var(--mono); font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--ink-3); display: block; margin-bottom: 8px; }
.felix-atelier .free-row { display: flex; gap: 8px; }
.felix-atelier .free-input { flex: 1; font-family: var(--sans); font-size: 14px; padding: 9px 12px; border: 1px solid var(--line-2); border-radius: 7px; background: #fffdf8; color: var(--ink); }
.felix-atelier .free-input:focus { outline: none; border-color: var(--gold); box-shadow: 0 0 0 3px var(--gold-soft); }
.felix-atelier .free-input::placeholder { color: var(--ink-3); }
.felix-atelier .free-send { flex: none; width: 38px; display: grid; place-items: center; border: none; border-radius: 7px; background: var(--gold); color: #fff; transition: background .15s ease; }
.felix-atelier .free-send:hover:not(:disabled) { background: var(--gold-deep); }
.felix-atelier .free-send:disabled { background: var(--line-2); color: var(--ink-3); cursor: default; }

/* Citation */
.felix-atelier .cite-card { max-width: 580px; }
.felix-atelier .cite-quote { margin: 0; padding: 0 0 0 20px; border-left: 3px solid var(--gold-line); font-family: var(--serif); font-style: italic; font-size: 17px; line-height: 1.62; color: var(--ink); text-wrap: pretty; }
.felix-atelier .cite-mark { display: block; color: var(--gold-line); margin: 0 0 0 16px; }
.felix-atelier .cite-source { font-family: var(--mono); font-size: 11.5px; letter-spacing: .03em; color: var(--ink-3); margin: 11px 0 0 20px; }
.felix-atelier .cite-note { font-family: var(--serif); font-size: 15px; line-height: 1.55; color: var(--ink-2); margin: 13px 0 0; max-width: 60ch; text-wrap: pretty; }

/* Alerte incohérence */
.felix-atelier .alert-card { max-width: 580px; border: 1px solid var(--terra-line); background: var(--terra-soft); border-radius: var(--r-md); padding: 14px 15px; box-shadow: var(--shadow-sm); }
.felix-atelier .alert-head { display: flex; align-items: center; gap: 9px; margin-bottom: 7px; }
.felix-atelier .alert-ic { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 7px; background: var(--terra); color: #fff; flex: none; }
.felix-atelier .alert-ic.ok { background: var(--sage); }
.felix-atelier .alert-title { font-family: var(--sans); font-weight: 700; font-size: 14px; color: var(--terra); }
.felix-atelier .alert-body { font-family: var(--serif); font-size: 15.5px; line-height: 1.55; color: var(--ink); margin: 0; text-wrap: pretty; }
.felix-atelier .alert-actions { display: flex; gap: 8px; margin-top: 12px; }
.felix-atelier .alert-btn { border-color: var(--terra-line) !important; background: #fff !important; color: var(--terra) !important; }
.felix-atelier .alert-btn:hover { border-color: var(--terra) !important; background: var(--terra-soft) !important; }
.felix-atelier .alert-resolves { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.felix-atelier .resolve-opt { display: flex; flex-direction: column; gap: 2px; text-align: left; padding: 10px 12px; border: 1px solid var(--terra-line); background: #fff; border-radius: 8px; transition: border-color .14s ease, background .14s ease; }
.felix-atelier .resolve-opt:hover { border-color: var(--terra); background: var(--terra-soft); }
.felix-atelier .ro-label { font-family: var(--sans); font-weight: 600; font-size: 14px; color: var(--ink); }
.felix-atelier .ro-desc { font-family: var(--serif); font-size: 14px; line-height: 1.4; color: var(--ink-2); }
.felix-atelier .alert-card.resolved { border-color: var(--sage-line); background: var(--sage-soft); }
.felix-atelier .alert-card.resolved .alert-title { color: var(--sage); }
.felix-atelier .alert-dismissed { display: flex; align-items: center; gap: 7px; font-family: var(--sans); font-size: 13px; color: var(--ink-3); }
.felix-atelier .redo { background: none; border: none; color: var(--gold-deep); font-weight: 600; font-size: 13px; text-decoration: underline; padding: 0; cursor: pointer; }

/* Composer */
.felix-atelier .composer-wrap { flex: none; border-top: 1px solid var(--line); background: rgba(243, 237, 225, .9); backdrop-filter: blur(10px); padding: 14px 24px 16px; }
.felix-atelier .composer-col { max-width: 768px; margin: 0 auto; }
.felix-atelier .composer { display: flex; align-items: flex-end; gap: 10px; background: #fffdf8; border: 1px solid var(--line-2); border-radius: 14px; padding: 8px 8px 8px 16px; box-shadow: var(--shadow-md); transition: border-color .15s ease, box-shadow .15s ease; }
.felix-atelier .composer:focus-within { border-color: var(--gold); box-shadow: 0 0 0 3px var(--gold-soft), var(--shadow-md); }
.felix-atelier .composer-ta { flex: 1; border: none; background: none; resize: none; font-family: var(--serif); font-size: 16px; line-height: 1.5; color: var(--ink); padding: 6px 0; max-height: 180px; }
.felix-atelier .composer-ta:focus { outline: none; }
.felix-atelier .composer-ta::placeholder { color: var(--ink-3); }
.felix-atelier .composer-send { flex: none; width: 40px; height: 40px; border: none; border-radius: 10px; background: var(--gold); color: #fff; display: grid; place-items: center; transition: background .15s ease, transform .06s ease; }
.felix-atelier .composer-send:hover:not(:disabled) { background: var(--gold-deep); }
.felix-atelier .composer-send:active { transform: translateY(1px); }
.felix-atelier .composer-send:disabled { background: var(--line-2); color: var(--ink-3); cursor: default; }
.felix-atelier .composer-hint { font-family: var(--mono); font-size: 11px; color: var(--ink-3); text-align: center; margin-top: 9px; }

@media (prefers-reduced-motion: reduce) {
  .felix-atelier .msg { animation: none; }
  .felix-atelier .typing span { animation: none; }
}
</style>
