/* Felix — Fiche personnage */
const { useState, useRef } = React;
const { h, Icons, Mono } = window.FelixUI;
const CHAT_URL = "Chat felix.html";

const REL_TYPES = ["Fille", "Fils", "Sœur", "Frère", "Père", "Mère", "Ami·e", "Rival·e", "Conjoint·e", "Mentor"];

function FicheApp() {
  const [f, setF] = useState({
    age: "42 ans",
    physique: "Sec, le visage marqué par le grand air. Démarche lente.",
    background: "Père marin, parti en mer lorsque Jean avait dix ans. Jamais revenu durablement. A grandi près du port qu'il évite aujourd'hui.",
    arc: "Idéalise son père : il reproduit ses départs sans en avoir conscience, jusqu'à la scène du quai où il devra enfin rester.",
    traits: "Taciturne, loyal, fuyant",
  });
  const [rels, setRels] = useState([
    { id: 1, name: "Camille", type: "Fille" },
    { id: 2, name: "Liane", type: "Sœur" },
  ]);
  const [adding, setAdding] = useState(false);
  const [newRel, setNewRel] = useState({ name: "", type: "Ami·e" });
  const [verify, setVerify] = useState(null); // null | {checks:[...]}
  const [saved, setSaved] = useState(false);

  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));

  const runVerify = () => {
    const checks = [
      { ok: !!f.age.trim(),        label: "Âge renseigné" },
      { ok: !!f.background.trim(), label: "Background renseigné" },
      { ok: !!f.arc.trim(),        label: "Arc narratif défini" },
      { ok: false, label: "« Fils unique » mentionné à la Scène 2",
        detail: "Contredit par la relation « Liane — sœur ». À trancher dans le chat.",
        action: true },
    ];
    setVerify({ checks });
  };

  const save = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2200);
  };

  const addRel = () => {
    if (!newRel.name.trim()) return;
    setRels((r) => [...r, { id: Date.now(), name: newRel.name.trim(), type: newRel.type }]);
    setNewRel({ name: "", type: "Ami·e" });
    setAdding(false);
  };
  const removeRel = (id) => setRels((r) => r.filter((x) => x.id !== id));

  const warnCount = verify ? verify.checks.filter((c) => !c.ok).length : 0;

  return h("div", { className: "page" }, [
    /* Barre */
    h("header", { className: "fbar", key: "bar" }, [
      h("a", { className: "back-link", href: CHAT_URL, key: "b" },
        [h(Icons.back, { size: 17, key: "i" }), "Retour au chat"]),
      h("div", { className: "fbar-brand", key: "br" }, [
        h("span", { className: "felix-mark sm", key: "m" }, h(Icons.felix, { size: 15 })),
        h("span", { className: "fbar-project", key: "p" }, "Rivière basse"),
      ]),
    ]),

    h("main", { className: "fwrap", key: "main" }, [
      /* En-tête personnage */
      h("div", { className: "char-head", key: "head" }, [
        h(Mono, { key: "av", size: 56 }, "J"),
        h("div", { className: "char-id", key: "id" }, [
          h("h1", { className: "char-name", key: "n" }, "Jean"),
          h("div", { className: "char-tags", key: "t" }, [
            h("span", { className: "badge", key: "b1" }, "Personnage principal"),
            h("span", { className: "char-ref mono", key: "b2" }, "#J-04"),
          ]),
        ]),
      ]),

      /* Carte formulaire */
      h("section", { className: "card form-card", key: "form" }, [
        h("div", { className: "grid2", key: "g" }, [
          h(Field, { key: "age", label: "Âge", value: f.age, onChange: set("age"),
            placeholder: "Âge du personnage" }),
          h(Field, { key: "phy", label: "Physique", value: f.physique, onChange: set("physique"),
            placeholder: "Description physique" }),
        ]),
        h(Field, { key: "bg", label: "Background", area: true, value: f.background,
          onChange: set("background"), placeholder: "Passé, origines, événements fondateurs…" }),
        h(Field, { key: "arc", label: "Arc narratif", area: true, value: f.arc,
          onChange: set("arc"), placeholder: "Comment le personnage évolue au fil du récit…" }),
        h(Field, { key: "tr", label: "Traits de caractère", value: f.traits,
          onChange: set("traits"), placeholder: "Traits, séparés par des virgules" }),

        verify ? h(VerifyPanel, { key: "vp", verify, warnCount, onClose: () => setVerify(null) }) : null,

        h("div", { className: "form-actions", key: "act" }, [
          h("a", { className: "btn btn-ghost", href: CHAT_URL, key: "cancel" }, "Annuler"),
          h("span", { className: "act-spacer", key: "sp" }),
          h("button", { className: "btn btn-verify", key: "verify", onClick: runVerify },
            [h(Icons.verify, { size: 16, key: "i" }), "Vérifier la cohérence"]),
          h("button", { className: "btn btn-primary", key: "save", onClick: save },
            saved ? [h(Icons.check, { size: 16, key: "c" }), "Enregistré"]
                  : "Enregistrer"),
        ]),
      ]),

      /* Relations */
      h("section", { className: "card rel-card", key: "rel" }, [
        h("div", { className: "rel-head", key: "h" }, [
          h("h2", { className: "rel-title", key: "t" }, "Relations"),
          h("button", { className: "btn btn-outline rel-add", key: "a",
            onClick: () => setAdding((v) => !v) },
            [h(Icons.plus, { size: 15, key: "i" }), "Ajouter"]),
        ]),
        h("div", { className: "rel-list", key: "l" }, [
          ...rels.map((r) =>
            h("div", { className: "rel-row", key: r.id }, [
              h("div", { className: "rel-left", key: "lf" }, [
                h(Mono, { key: "av", size: 30, gold: false }, r.name[0]),
                h("span", { className: "rel-name", key: "n" }, r.name),
                h("span", { className: "badge badge-rel", key: "ty" }, r.type),
              ]),
              h("button", { className: "rel-x", key: "x", onClick: () => removeRel(r.id),
                title: "Supprimer la relation" }, h(Icons.close, { size: 16 })),
            ])),
          adding ? h("div", { className: "rel-add-row", key: "addrow" }, [
            h("input", { key: "name", className: "input rel-input",
              placeholder: "Nom du personnage", value: newRel.name, autoFocus: true,
              onChange: (e) => setNewRel((s) => ({ ...s, name: e.target.value })),
              onKeyDown: (e) => { if (e.key === "Enter") addRel(); } }),
            h("select", { key: "type", className: "input rel-select", value: newRel.type,
              onChange: (e) => setNewRel((s) => ({ ...s, type: e.target.value })) },
              REL_TYPES.map((t) => h("option", { key: t, value: t }, t))),
            h("button", { key: "ok", className: "btn btn-primary", onClick: addRel }, "Ajouter"),
            h("button", { key: "no", className: "btn btn-ghost", onClick: () => setAdding(false) },
              h(Icons.close, { size: 16 })),
          ]) : null,
        ]),
      ]),

      h("p", { className: "fiche-foot mono", key: "ft" },
        "Les fiches alimentent la mémoire de Felix. Il les met à jour au fil de vos échanges."),
    ]),
  ]);
}

function Field({ label, value, onChange, placeholder, area }) {
  return h("div", { className: "field" }, [
    h("label", { className: "field-label", key: "l" }, label),
    area
      ? h("textarea", { key: "i", className: "textarea", rows: 3, value, onChange, placeholder })
      : h("input", { key: "i", className: "input", value, onChange, placeholder }),
  ]);
}

function VerifyPanel({ verify, warnCount, onClose }) {
  const allOk = warnCount === 0;
  return h("div", { className: "verify-panel " + (allOk ? "ok" : "warn") }, [
    h("div", { className: "verify-top", key: "t" }, [
      h("span", { className: "verify-ic", key: "i" },
        h(allOk ? Icons.check : Icons.alert, { size: 15 })),
      h("span", { className: "verify-sum", key: "s" },
        allOk ? "Tout est cohérent" : warnCount + " point à vérifier"),
      h("button", { className: "verify-close", key: "c", onClick: onClose },
        h(Icons.close, { size: 15 })),
    ]),
    h("ul", { className: "verify-list", key: "l" },
      verify.checks.map((c, i) =>
        h("li", { className: "verify-item" + (c.ok ? "" : " bad"), key: i }, [
          h("span", { className: "vi-ic", key: "ic" },
            h(c.ok ? Icons.check : Icons.alert, { size: 13 })),
          h("div", { className: "vi-main", key: "m" }, [
            h("span", { className: "vi-label", key: "l" }, c.label),
            c.detail ? h("span", { className: "vi-detail", key: "d" }, c.detail) : null,
          ]),
          c.action ? h("a", { className: "vi-action", key: "a", href: CHAT_URL },
            ["Régler dans le chat", h(Icons.arrow, { size: 12, key: "ar" })]) : null,
        ]))),
  ]);
}

window.FicheApp = FicheApp;
