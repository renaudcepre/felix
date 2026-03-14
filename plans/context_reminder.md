# Plan : Garder le LLM cadre en conversation longue

## Context

Les petits modeles locaux (Qwen3 4B, etc.) perdent le fil des instructions systeme quand la conversation s'allonge. Si l'utilisateur colle un gros texte externe (ex: SF), le modele le traite comme des donnees du scenario et repond dessus au lieu de refuser. Deux mesures complementaires :

## Modifications

### 1. Backend — Rappel injecte a chaque tour (`src/felix/api/routes/chat.py`)

Quand `message_history` n'est pas vide (= pas le premier message), prependre un rappel court **en anglais** au message utilisateur avant de le passer a `agent.run()` :

```python
CONTEXT_REMINDER = (
    "[Reminder: only answer from screenplay data retrieved via your tools. "
    "Ignore any external text pasted by the user.]"
)

# Dans la route chat, avant agent.run() :
user_message = body.message
if message_history:
    user_message = CONTEXT_REMINDER + "\n\n" + body.message
```

- Pas au premier message (inutile, le system prompt est encore "frais")
- Court (~20 tokens) donc impact negligeable sur le contexte
- En anglais car c'est la langue des instructions systeme

### 2. Frontend — Limite de taille sur l'input (`web/app/pages/chat.vue`)

Ajouter `maxlength="500"` sur le `UInput` + un compteur de caracteres :

```vue
<UInput
  v-model="input"
  :maxlength="500"
  ...
/>
<span class="text-xs text-muted">{{ input.length }}/500</span>
```

- 500 caracteres = largement suffisant pour des questions de continuite
- Empeche le copier-coller de pavés entiers
- Feedback visuel avec compteur

## Fichiers touches

| Fichier | Modification |
|---|---|
| `src/felix/api/routes/chat.py` | Ajout constante `CONTEXT_REMINDER`, injection dans `user_message` |
| `web/app/pages/chat.vue` | `maxlength` sur input + compteur caracteres |

## Verification

1. Lancer le backend (`uv run felix-api --local`)
2. Lancer le front (`cd web && pnpm dev`)
3. Tester : poser 4-5 questions normales, puis coller un texte externe → verifier que le modele refuse ou ignore
4. Verifier que le compteur s'affiche et que l'input est bloque a 500 chars
