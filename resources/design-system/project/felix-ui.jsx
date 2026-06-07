/* Felix — primitives partagées (icônes + petits composants).
   Exporté sur window pour les deux pages. */
const { createElement: h } = React;

function Icon({ d, paths, size = 18, stroke = 1.6, fill = "none", style }) {
  return h("svg", {
    width: size, height: size, viewBox: "0 0 24 24", fill,
    stroke: "currentColor", strokeWidth: stroke,
    strokeLinecap: "round", strokeLinejoin: "round", style
  }, paths ? paths.map((p, i) => h("path", { key: i, d: p })) : h("path", { d }));
}

const Icons = {
  send:   (p) => h(Icon, { ...p, d: "M12 19V5 M6 11l6-6 6 6" }),
  felix:  (p) => h(Icon, { ...p, paths: ["M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"] }),
  verify: (p) => h(Icon, { ...p, paths: ["M12 3l7 3v5c0 4.2-2.8 7.6-7 9-4.2-1.4-7-4.8-7-9V6z", "M9 11.5l2 2 4-4.5"] }),
  alert:  (p) => h(Icon, { ...p, paths: ["M10.3 3.8 1.9 18a1.9 1.9 0 0 0 1.7 2.9h16.8A1.9 1.9 0 0 0 22 18L13.7 3.8a1.9 1.9 0 0 0-3.4 0z", "M12 9v4", "M12 17h.01"] }),
  quote:  (p) => h(Icon, { ...p, paths: ["M7 7H4v6h5V9 M17 7h-3v6h5V9"] , fill: "currentColor", stroke: "none" }),
  fiche:  (p) => h(Icon, { ...p, paths: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z", "M14 3v5h5", "M9 13h4", "M9 17h6"] }),
  plus:   (p) => h(Icon, { ...p, d: "M12 5v14 M5 12h14" }),
  back:   (p) => h(Icon, { ...p, d: "M15 18l-6-6 6-6" }),
  arrow:  (p) => h(Icon, { ...p, d: "M5 12h14 M13 6l6 6-6 6" }),
  close:  (p) => h(Icon, { ...p, d: "M6 6l12 12 M18 6 6 18" }),
  check:  (p) => h(Icon, { ...p, d: "M5 12.5l4.5 4.5L19 7" }),
  pencil: (p) => h(Icon, { ...p, paths: ["M12 20h9", "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"] }),
  people: (p) => h(Icon, { ...p, paths: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8", "M22 21v-2a4 4 0 0 0-3-3.9", "M16 3.1A4 4 0 0 1 16 11"] }),
  dot:    (p) => h(Icon, { ...p, paths: ["M12 12h.01"], stroke: 3 }),
};

/* Monogramme rond */
function Mono({ children, size = 38, gold = true, style }) {
  return h("span", {
    className: "mono-avatar",
    style: { width: size, height: size, fontSize: size * 0.42,
      ...(gold ? {} : { background: "var(--card-2)", borderColor: "var(--line-2)", color: "var(--ink-2)" }),
      ...style }
  }, children);
}

window.FelixUI = { h, Icon, Icons, Mono };
