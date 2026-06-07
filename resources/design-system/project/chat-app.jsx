/* Felix — application Chat */
const { useState, useRef, useEffect, useCallback } = React;
const { h, Icons, Mono } = window.FelixUI;
const FICHE_URL = "Fiche personnage.html";

const { useTweaks, TweaksPanel, TweakSection, TweakColor, TweakRadio } = window;
const ACCENTS = {
  ocre:    ["#a9772a", "#8a5f1f", "#f0e3c8", "#e3cd9b"],
  ardoise: ["#3f5f72", "#2f4a59", "#dce7ec", "#b6cdd8"],
  prune:   ["#6d4b6b", "#543853", "#ece1ea", "#d4bdd0"],
  cuir:    ["#8a5a3c", "#6e4530", "#ecdcc6", "#ddc1a0"],
};
const FONTS = {
  "Newsreader":   '"Newsreader", Georgia, serif',
  "Spectral":     '"Spectral", Georgia, serif',
  "Source Serif": '"Source Serif 4", Georgia, serif',
};
const TWEAK_DEFAULTS = { accent: ACCENTS.ocre, recit: "Newsreader" };

let _id = 100;
const uid = () => ++_id;

/* ---------- Données initiales du fil ---------- */
const seed = () => ([
  { id: uid(), role: "felix", kind: "text",
    body: "Bonjour. On reprend *Rivière basse* là où on s'est arrêtés — la scène du quai, à l'aube. Sur quoi veux-tu travailler aujourd'hui ?" },
  { id: uid(), role: "user", kind: "text",
    body: "J'aimerais creuser le passé de Jean. Son père était marin, parti quand Jean avait dix ans." },
  { id: uid(), role: "felix", kind: "tool", tool: "fiche",
    title: "Fiche mise à jour", subject: "Jean", field: "Background",
    added: "Père marin, parti en mer lorsque Jean avait dix ans. Jamais revenu durablement." },
  { id: uid(), role: "felix", kind: "text",
    body: "C'est noté sur sa fiche. Ce départ peut devenir le foyer de son rapport au manque — utile pour la suite. Pour bien l'ancrer :" },
  { id: uid(), role: "felix", kind: "choice", answered: false,
    question: "Comment veux-tu que ce passé pèse sur le présent de Jean ?",
    options: [
      { k: "A", label: "Il fuit l'eau", desc: "Jean évite le port, ce qui crée une tension géographique dans le récit." },
      { k: "B", label: "Il idéalise son père", desc: "Il répète ses choix sans le savoir — l'ironie tragique se met en place." },
      { k: "C", label: "Il lui en veut", desc: "Une colère sourde contamine peu à peu ses liens, surtout avec Camille." },
    ] },
  { id: uid(), role: "felix", kind: "cite",
    quote: "Jean s'arrête au bout du quai. Il ne regarde pas l'eau — il regarde la ligne où elle s'arrête.",
    source: "Scène 4 · Le quai, aube — p. 12",
    note: "Tu as déjà cette image. Elle colle bien avec l'idée d'évitement, si tu veux la garder cohérente." },
  { id: uid(), role: "felix", kind: "alert", status: "open",
    title: "Incohérence possible",
    body: "Jean est présenté comme « fils unique » (Scène 2), mais une sœur, Liane, apparaît à la Scène 9.",
    resolves: [
      { id: "keep-liane", label: "Garder Liane", desc: "Retirer « fils unique » de la Scène 2." },
      { id: "keep-only",  label: "Garder « fils unique »", desc: "Supprimer le personnage Liane du récit." },
    ] },
]);

/* ---------- Réponses scriptées de Felix ---------- */
const followForChoice = (opt) => {
  const map = {
    A: { arc: "Évitement de l'eau : Jean contourne le port, jusqu'à la confrontation finale au quai.",
         text: "Bien. J'ai inscrit cet axe dans son arc. La scène du quai devient alors le point de bascule — c'est là qu'il devra enfin s'approcher." },
    B: { arc: "Répétition du père : Jean reproduit les départs qu'il a subis, sans en avoir conscience.",
         text: "Noté dans son arc. Pense à semer un détail concret qu'il hérite de son père — un geste, un objet — pour rendre la répétition lisible à l'écran." },
    C: { arc: "Colère héritée : le ressentiment envers le père déteint sur sa relation à Camille.",
         text: "Inscrit. Ça donne du grain à sa relation avec Camille — leur tension n'est plus gratuite, elle a une source." },
  };
  return map[opt.k] || map.A;
};

const cannedReplies = [
  "Intéressant. Veux-tu que je le reporte sur une fiche, ou qu'on le garde comme piste pour l'instant ?",
  "Je vois où tu vas. Donne-moi une scène où ça se manifeste, et je vérifie la cohérence avec le reste.",
  "D'accord. Ça reste cohérent avec ce qu'on a posé — je n'ai rien à signaler de ce côté.",
];

/* ========================================================== */
function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  useEffect(() => {
    const r = document.documentElement.style;
    const a = t.accent || ACCENTS.ocre;
    r.setProperty("--gold", a[0]);
    r.setProperty("--gold-deep", a[1]);
    r.setProperty("--gold-soft", a[2]);
    r.setProperty("--gold-line", a[3]);
    r.setProperty("--serif", FONTS[t.recit] || FONTS.Newsreader);
  }, [t.accent, t.recit]);

  const [messages, setMessages] = useState(seed);
  const [draft, setDraft] = useState("");
  const [typing, setTyping] = useState(false);
  const scrollRef = useRef(null);
  const taRef = useRef(null);

  const append = useCallback((msg) => setMessages((m) => [...m, { id: uid(), ...msg }]), []);
  const patch = useCallback((id, fn) =>
    setMessages((m) => m.map((x) => (x.id === id ? fn(x) : x))), []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, typing]);

  const felixSays = (items, delay = 650) => {
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      items.forEach((it) => append(it));
    }, delay);
  };

  const sendText = (text) => {
    const t = text.trim();
    if (!t) return;
    append({ role: "user", kind: "text", body: t });
    setDraft("");
    if (taRef.current) taRef.current.style.height = "auto";
    const reply = cannedReplies[Math.floor(Math.random() * cannedReplies.length)];
    felixSays([{ role: "felix", kind: "text", body: reply }]);
  };

  const pickChoice = (msg, opt) => {
    patch(msg.id, (x) => ({ ...x, answered: true, chosen: opt.k }));
    append({ role: "user", kind: "text", body: opt.label });
    const f = followForChoice(opt);
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      append({ role: "felix", kind: "tool", tool: "fiche",
        title: "Fiche mise à jour", subject: "Jean", field: "Arc narratif", added: f.arc });
      append({ role: "felix", kind: "text", body: f.text });
    }, 720);
  };

  const freeChoice = (msg, text) => {
    const t = text.trim();
    if (!t) return;
    patch(msg.id, (x) => ({ ...x, answered: true, chosen: "libre" }));
    sendText(t);
  };

  const setAlertStatus = (msg, status) => patch(msg.id, (x) => ({ ...x, status }));

  const resolveAlert = (msg, res) => {
    const resolvedText = res.id === "keep-liane"
      ? "« Fils unique » retiré de la Scène 2. Liane conservée comme sœur de Jean."
      : "Personnage Liane supprimé. Jean reste fils unique.";
    patch(msg.id, (x) => ({ ...x, status: "resolved", resolution: resolvedText }));
    if (res.id === "keep-liane") {
      setTyping(true);
      setTimeout(() => {
        setTyping(false);
        append({ role: "felix", kind: "tool", tool: "people",
          title: "Relation ajoutée", subject: "Jean", field: "Relations", added: "Liane — sœur" });
      }, 600);
    }
  };

  return h("div", { className: "app" }, [
    h(TopBar, { key: "top" }),
    h("div", { className: "thread-wrap", ref: scrollRef, key: "tw" },
      h("div", { className: "thread" }, [
        h(DayMark, { key: "dm", label: "Aujourd'hui" }),
        ...messages.map((m) =>
          h(MessageRow, { key: m.id, msg: m, onPick: pickChoice, onFree: freeChoice,
            onResolve: resolveAlert, onStatus: setAlertStatus })),
        typing ? h(Typing, { key: "typ" }) : null,
        h("div", { key: "pad", style: { height: 8 } }),
      ])),
    h(Composer, { key: "cp", draft, setDraft, onSend: sendText, taRef }),
    h(TweaksPanel, { key: "tweaks" }, [
      h(TweakSection, { key: "s1", label: "Accent" }),
      h(TweakColor, { key: "ac", label: "Couleur", value: t.accent,
        options: [ACCENTS.ocre, ACCENTS.ardoise, ACCENTS.prune, ACCENTS.cuir],
        onChange: (v) => setTweak("accent", v) }),
      h(TweakSection, { key: "s2", label: "Récit" }),
      h(TweakRadio, { key: "ft", label: "Typographie", value: t.recit,
        options: ["Newsreader", "Spectral", "Source Serif"],
        onChange: (v) => setTweak("recit", v) }),
    ]),
  ]);
}

/* ---------- Barre du haut ---------- */
function TopBar() {
  return h("header", { className: "topbar" }, [
    h("div", { className: "tb-left", key: "l" }, [
      h("span", { className: "felix-mark", key: "m" }, h(Icons.felix, { size: 18 })),
      h("span", { className: "felix-word", key: "w" }, "Felix"),
      h("span", { className: "tb-sep", key: "s" }),
      h("span", { className: "tb-project", key: "p" }, "Rivière basse"),
    ]),
    h("div", { className: "tb-right", key: "r" }, [
      h("span", { className: "tb-save", key: "sv" }, [
        h("span", { className: "save-dot", key: "d" }), "Enregistré",
      ]),
      h("a", { className: "btn btn-outline", href: FICHE_URL, key: "ch" },
        [h(Icons.people, { size: 16, key: "i" }), "Personnages"]),
    ]),
  ]);
}

function DayMark({ label }) {
  return h("div", { className: "daymark" }, h("span", null, label));
}

/* ---------- Indicateur de frappe ---------- */
function Typing() {
  return h("div", { className: "msg msg-felix" }, [
    h("div", { className: "msg-av", key: "a" }, h(Mono, { size: 32 }, "F")),
    h("div", { className: "msg-main", key: "b" },
      h("div", { className: "typing" }, [
        h("span", { key: 1 }), h("span", { key: 2 }), h("span", { key: 3 }),
      ])),
  ]);
}

/* ---------- Routage des messages ---------- */
function MessageRow({ msg, onPick, onFree, onResolve, onStatus }) {
  if (msg.role === "user")
    return h("div", { className: "msg msg-user" },
      h("div", { className: "bubble" }, msg.body));

  // Felix
  const inner = (() => {
    switch (msg.kind) {
      case "text":  return h(FelixText, { body: msg.body });
      case "tool":  return h(ToolCard, { msg });
      case "choice":return h(ChoiceBlock, { msg, onPick, onFree });
      case "cite":  return h(CiteBlock, { msg });
      case "alert": return h(AlertBlock, { msg, onResolve, onStatus });
      default: return null;
    }
  })();

  return h("div", { className: "msg msg-felix" }, [
    h("div", { className: "msg-av", key: "a" }, h(Mono, { size: 32 }, "F")),
    h("div", { className: "msg-main", key: "b" }, inner),
  ]);
}

/* Met *en valeur* le texte entre astérisques (titres d'œuvres) */
function FelixText({ body }) {
  const parts = body.split(/(\*[^*]+\*)/g).map((p, i) =>
    p.startsWith("*") && p.endsWith("*")
      ? h("em", { key: i, className: "work" }, p.slice(1, -1))
      : p);
  return h("p", { className: "felix-text" }, parts);
}

/* ---------- Carte « tool use » ---------- */
function ToolCard({ msg }) {
  const TIcon = msg.tool === "people" ? Icons.people : Icons.fiche;
  return h("div", { className: "tool-card" }, [
    h("div", { className: "tool-head", key: "h" }, [
      h("span", { className: "tool-ic", key: "i" }, h(TIcon, { size: 15 })),
      h("span", { className: "tool-label", key: "l" }, msg.title),
      h("span", { className: "tool-spacer", key: "sp" }),
      h("a", { className: "tool-link", href: FICHE_URL, key: "a" },
        ["Voir la fiche", h(Icons.arrow, { size: 13, key: "ar" })]),
    ]),
    h("div", { className: "tool-body", key: "b" }, [
      h("div", { className: "tool-meta", key: "m" }, [
        h("span", { className: "tool-subj", key: "s" }, msg.subject),
        h("span", { className: "tool-fdot", key: "d" }),
        h("span", { className: "tool-field", key: "f" }, msg.field),
      ]),
      h("div", { className: "tool-added", key: "ad" }, [
        h("span", { className: "tool-plus", key: "p" }, "+ ajouté"),
        h("span", { className: "tool-text", key: "t" }, msg.added),
      ]),
    ]),
  ]);
}

/* ---------- Bloc à choix multiple + champ libre ---------- */
function ChoiceBlock({ msg, onPick, onFree }) {
  const [free, setFree] = useState("");
  const done = msg.answered;
  return h("div", { className: "choice-card" + (done ? " is-done" : "") }, [
    h("div", { className: "choice-q", key: "q" }, msg.question),
    h("div", { className: "choice-opts", key: "o" },
      msg.options.map((opt) =>
        h("button", {
          key: opt.k,
          className: "choice-opt" +
            (done && msg.chosen === opt.k ? " chosen" : "") +
            (done && msg.chosen !== opt.k ? " dim" : ""),
          disabled: done,
          onClick: () => onPick(msg, opt),
        }, [
          h("span", { className: "opt-k", key: "k" }, done && msg.chosen === opt.k
            ? h(Icons.check, { size: 14 }) : opt.k),
          h("span", { className: "opt-main", key: "m" }, [
            h("span", { className: "opt-label", key: "l" }, opt.label),
            h("span", { className: "opt-desc", key: "d" }, opt.desc),
          ]),
        ]))),
    done ? null : h("div", { className: "choice-free", key: "fr" }, [
      h("span", { className: "free-or", key: "or" }, "ou précise"),
      h("div", { className: "free-row", key: "rw" }, [
        h("input", {
          key: "in", className: "free-input", value: free,
          placeholder: "Écris ta propre réponse…",
          onChange: (e) => setFree(e.target.value),
          onKeyDown: (e) => { if (e.key === "Enter") { onFree(msg, free); setFree(""); } },
        }),
        h("button", {
          key: "bt", className: "free-send", disabled: !free.trim(),
          onClick: () => { onFree(msg, free); setFree(""); },
        }, h(Icons.send, { size: 16 })),
      ]),
    ]),
  ]);
}

/* ---------- Citation d'extrait ---------- */
function CiteBlock({ msg }) {
  return h("div", { className: "cite-card" }, [
    h("span", { className: "cite-mark", key: "m" }, h(Icons.quote, { size: 20 })),
    h("blockquote", { className: "cite-quote", key: "q" }, msg.quote),
    h("div", { className: "cite-source", key: "s" }, msg.source),
    msg.note ? h("p", { className: "cite-note", key: "n" }, msg.note) : null,
  ]);
}

/* ---------- Alerte d'incohérence ---------- */
function AlertBlock({ msg, onResolve, onStatus }) {
  if (msg.status === "dismissed")
    return h("div", { className: "alert-dismissed" }, [
      h(Icons.dot, { size: 14, key: "d" }), "Incohérence ignorée.",
      h("button", { className: "redo", key: "r", onClick: () => onStatus(msg, "open") }, "Revoir"),
    ]);

  if (msg.status === "resolved")
    return h("div", { className: "alert-card resolved" }, [
      h("div", { className: "alert-head", key: "h" }, [
        h("span", { className: "alert-ic ok", key: "i" }, h(Icons.check, { size: 15 })),
        h("span", { className: "alert-title", key: "t" }, "Incohérence résolue"),
      ]),
      h("p", { className: "alert-body", key: "b" }, msg.resolution),
    ]);

  const resolving = msg.status === "resolving";
  return h("div", { className: "alert-card" }, [
    h("div", { className: "alert-head", key: "h" }, [
      h("span", { className: "alert-ic", key: "i" }, h(Icons.alert, { size: 15 })),
      h("span", { className: "alert-title", key: "t" }, msg.title),
    ]),
    h("p", { className: "alert-body", key: "b" }, msg.body),
    resolving
      ? h("div", { className: "alert-resolves", key: "rs" },
          msg.resolves.map((r) =>
            h("button", { key: r.id, className: "resolve-opt", onClick: () => onResolve(msg, r) }, [
              h("span", { className: "ro-label", key: "l" }, r.label),
              h("span", { className: "ro-desc", key: "d" }, r.desc),
            ])))
      : h("div", { className: "alert-actions", key: "ac" }, [
          h("button", { className: "btn btn-outline alert-btn", key: "s",
            onClick: () => onStatus(msg, "resolving") },
            [h(Icons.verify, { size: 15, key: "v" }), "Résoudre"]),
          h("button", { className: "btn btn-ghost", key: "i",
            onClick: () => onStatus(msg, "dismissed") }, "Ignorer"),
        ]),
  ]);
}

/* ---------- Composer ---------- */
function Composer({ draft, setDraft, onSend, taRef }) {
  const grow = (el) => { el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 180) + "px"; };
  return h("div", { className: "composer-wrap" },
    h("div", { className: "composer-col" }, [
      h("div", { className: "composer", key: "c" }, [
        h("textarea", {
          key: "ta", ref: taRef, className: "composer-ta", rows: 1, value: draft,
          placeholder: "Écris à Felix… (idée, scène, question)",
          onChange: (e) => { setDraft(e.target.value); grow(e.target); },
          onKeyDown: (e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(draft); }
          },
        }),
        h("button", {
          key: "sb", className: "composer-send", disabled: !draft.trim(),
          onClick: () => onSend(draft), title: "Envoyer",
        }, h(Icons.send, { size: 18 })),
      ]),
      h("div", { className: "composer-hint", key: "h" },
        "Felix peut modifier les fiches et signaler les incohérences du scénario."),
    ]));
}

window.ChatApp = App;
