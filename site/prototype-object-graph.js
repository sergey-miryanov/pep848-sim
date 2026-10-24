// @ts-nocheck
// PROTOTYPE, not for main (#151): three ways to draw the selected preset's object
// graph, switched by ?variant= and the floating bar. Each draws the same sample,
// which tools/prototype_object_graph.py writes from the presets' real shapes.
//
// A: a small diagram for each structure, in the widget under its controls.
// B: one force-directed diagram for each preset, after its paragraph under
//    "The workloads", all five at once.
// C: a row for each structure in the widget, its diagram beside its builds and
//    lifetimes on the allocation clock.

import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7.9.0/+esm";

const DATA = await (await fetch("prototype-object-graph.json")).json();
const widget = document.querySelector("gc-widget#home-widget");
const SVG = "http://www.w3.org/2000/svg";

const variant = () => new URLSearchParams(location.search).get("variant") ?? "A";
const entry = () => widget.shadowRoot?.querySelector(".entries select")?.value;

const STYLE = `
  .proto { margin: 0 0 24px; padding: 12px 0; border-top: 1px solid var(--grid); border-bottom: 1px solid var(--grid); }
  .proto h3 { margin: 0 0 4px; font-size: 13px; font-weight: 600; }
  .proto .note { margin: 0 0 10px; font-size: 12px; color: var(--text-secondary); }
  .proto .note .swatch { display: inline-block; width: 14px; height: 0; border-top: 2px solid var(--proto-cycle); vertical-align: middle; margin: 0 4px; }
  .proto svg { display: block; overflow: visible; }
  .proto .link { stroke: var(--proto-link); stroke-width: 1; fill: none; }
  .proto .cycle { stroke: var(--proto-cycle); stroke-width: 1.5; }
  .proto .node { fill: var(--text-secondary); }
  .proto .head { fill: var(--text-primary); }
  .proto .more { fill: var(--text-muted, #898781); font-size: 9px; }
  .proto .root { fill: var(--surface); stroke: var(--text-primary); }
  .proto .rootlabel { fill: var(--text-primary); font-size: 10px; font-weight: 600; }
  .proto .caption { font-size: 12px; color: var(--text-secondary); max-width: 230px; }
  .proto .caption b { color: var(--text-primary); font-weight: 600; }
  .proto .strip { display: flex; gap: 28px; overflow-x: auto; align-items: flex-start; padding-bottom: 4px; }
  .proto .group { display: grid; gap: 6px; }
  .proto .group > .held { font-size: 12px; font-weight: 600; color: var(--text-primary); }
  .proto .group > .members { display: flex; gap: 20px; align-items: flex-start; }
  .proto figure { margin: 0; display: grid; gap: 4px; justify-items: start; min-width: 150px; }
  .proto .held-by { stroke: var(--text-secondary); stroke-dasharray: 3 2; stroke-width: 1.2; }
  .proto .rows { display: grid; grid-template-columns: 150px 210px 1fr; gap: 6px 16px; align-items: center; }
  .proto .rows .axis text { fill: var(--text-muted, #898781); font-size: 10px; }
  .proto .rows .axis line { stroke: var(--baseline); }
  .proto .build { fill: var(--text-secondary); }
  .proto .alive { fill: var(--text-secondary); opacity: 0.22; }
  .proto .churn { fill: var(--text-muted, #898781); opacity: 0.25; }
  .proto .rowhead { grid-column: 1 / -1; font-size: 12px; font-weight: 600; margin-top: 4px; }
`;

const TOKENS = `
  :root { --proto-link: #b9b8b0; --proto-cycle: #e34948; --proto-s0: #898781; --proto-s1: #52514e; --proto-s2: #2a78d6; --proto-s3: #eda100; --grid: #e1e0d9; --baseline: #c3c2b7; --text-muted: #898781; }
  @media (prefers-color-scheme: dark) {
    :root { --proto-link: #55544f; --proto-cycle: #e66767; --proto-s0: #898781; --proto-s1: #c3c2b7; --proto-s2: #3987e5; --proto-s3: #c98500; --grid: #2c2c2a; --baseline: #383835; }
  }
`;
// The widget's shadow root keeps its own tokens; these two it lacks.
const SHADOW_TOKENS = `
  :host { --proto-link: #b9b8b0; --proto-cycle: #e34948; }
  @media (prefers-color-scheme: dark) { :host { --proto-link: #55544f; --proto-cycle: #e66767; } }
`;

const pageStyle = document.createElement("style");
pageStyle.textContent = TOKENS + STYLE;
document.head.append(pageStyle);

const el = (name, attrs = {}, parent) => {
  const made = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attrs)) made.setAttribute(key, value);
  parent?.append(made);
  return made;
};
const html = (tag, className, text) => {
  const made = document.createElement(tag);
  if (className) made.className = className;
  if (text !== undefined) made.innerHTML = text;
  return made;
};
const size = (kb) => (kb < 1000 ? `${kb.toLocaleString("en")} kB` : `${(kb / 1000).toLocaleString("en", { maximumFractionDigits: 1 })} MB`);
const shapeName = (s) => (s.parameter == null ? s.shape : `${s.shape}(${s.parameter})`);

function timing(s) {
  if (s.rebuild_interval == null) {
    return s.lifetime == null ? "built at start-up, kept to shutdown" : `built once, lives ${size(s.lifetime)}`;
  }
  const collect = s.full_collections ? ", gc.collect() before and after" : "";
  const lives = s.lifetime ? `each lives ${size(s.lifetime)}` : "each dropped as soon as built";
  return `built ${s.builds.toLocaleString("en")}×, every ${size(s.rebuild_interval)}, ${lives}${collect}`;
}

function churnText(c) {
  const cycles = c.cycle_share ? `${Math.round(c.cycle_share * 100)}% in cycles of ${c.cycle_size}` : "no cycles";
  const long = c.long_share ? `, ${Math.round(c.long_share * 100)}% live ${size(c.long_lifetimes[0])}–${size(c.long_lifetimes[1])}` : "";
  return `lifetimes about ${size(c.lifetime_mean)}, ${cycles}${long}`;
}

/** Each sampled object's place: its level, and its order there under its parent's. */
function layered(s) {
  const byId = new Map(s.nodes.map((n) => [n.id, n]));
  const parent = new Map();
  for (const l of s.links) {
    if (byId.get(l.source).level + 1 === byId.get(l.target).level && !parent.has(l.target)) parent.set(l.target, l.source);
  }
  const levels = [];
  for (const n of s.nodes) (levels[n.level] ??= []).push(n.id);
  const order = new Map();
  levels.forEach((ids, depth) => {
    if (depth) ids.sort((a, b) => order.get(parent.get(a)) - order.get(parent.get(b)) || a - b);
    ids.forEach((id, k) => order.set(id, k));
  });
  return { byId, levels, order };
}

/** Draw links: a pair both ways bends apart, a self-link loops above. */
function drawLinks(g, links, at, bend = 6) {
  const has = new Set(links.map((l) => `${l.source}>${l.target}`));
  for (const l of links) {
    const [x1, y1] = at(l.source);
    const [x2, y2] = at(l.target);
    const cls = `link${l.cycle ? " cycle" : ""}`;
    if (l.source === l.target) {
      el("circle", { cx: x1, cy: y1 - 6, r: 5, class: cls }, g);
    } else if (has.has(`${l.target}>${l.source}`)) {
      const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
      const side = l.source < l.target ? 1 : -1;
      el("path", { d: `M${x1},${y1} Q${mx - (dy / len) * bend * side},${my + (dx / len) * bend * side} ${x2},${y2}`, class: cls }, g);
    } else {
      el("line", { x1, y1, x2, y2, class: cls }, g);
    }
  }
}

/** A structure's sample, level by level: its root on top. */
function sampleSvg(s, { gap = 26, spacing = 11, r = 3.2, more = true } = {}) {
  const { byId, levels, order } = layered(s);
  const widest = Math.max(...levels.map((ids) => ids.length));
  const width = Math.max(60, widest * spacing + 24) + (more ? 56 : 0);
  const height = (levels.length - 1) * gap + 30;
  const at = (id) => {
    const n = byId.get(id);
    const count = levels[n.level].length;
    return [(width - (more ? 56 : 0)) / 2 + (order.get(id) - (count - 1) / 2) * spacing, 12 + n.level * gap];
  };
  const svg = el("svg", { width, height: height + (more ? 8 : 0), viewBox: `0 0 ${width} ${height + (more ? 8 : 0)}` });
  drawLinks(el("g", {}, svg), s.links, at);
  const nodes = el("g", {}, svg);
  for (const n of s.nodes) {
    const [x, y] = at(n.id);
    el("circle", { cx: x, cy: y, r: n.id === 0 ? r + 1.3 : r, class: n.id === 0 ? "node head" : "node" }, nodes);
  }
  // What each level's objects hold beyond the sample: one label for a level whose
  // objects all hold as many, one per object on a narrow level, a sum on a wide one.
  if (more) {
    levels.forEach((ids) => {
      const counts = ids.map((id) => byId.get(id).more);
      if (!counts.some(Boolean)) return;
      const label = (x, y, text) => { el("text", { x, y, class: "more" }, nodes).textContent = text; };
      const [lastX, lastY] = at(ids.at(-1));
      if (counts.every((c) => c === counts[0]) && ids.length > 1) label(lastX + 6, lastY + 3, `+${counts[0].toLocaleString("en")} each`);
      else if (ids.length <= 4) ids.forEach((id, k) => { if (counts[k]) { const [x, y] = at(id); label(x + 5, y + 3, `+${counts[k].toLocaleString("en")}`); } });
      else label(lastX + 6, lastY + 3, `+${counts.reduce((a, b) => a + b, 0).toLocaleString("en")} more`);
    });
  }
  return svg;
}

function caption(s) {
  return html("div", "caption", `<b>${s.label}</b><br>${shapeName(s)}, × ${s.size.toLocaleString("en")} (${size(s.size)})<br>${timing(s)}`);
}

function churnSvg(c) {
  const svg = el("svg", { width: 120, height: 50, viewBox: "0 0 120 50" });
  const g = el("g", {}, svg);
  for (let k = 0; k < 9; k++) el("circle", { cx: 8 + k * 13, cy: 14, r: 2.6, class: "node", opacity: 0.55 }, g);
  if (c.cycle_share) {
    for (let k = 0; k < 2; k++) {
      const x = 20 + k * 50;
      const pts = Array.from({ length: c.cycle_size }, (_, j) => [x + j * 14, 38]);
      pts.forEach(([px, py]) => el("circle", { cx: px, cy: py, r: 2.6, class: "node" }, g));
      const links = pts.map((_, j) => ({ source: j, target: (j + 1) % pts.length, cycle: true }));
      if (pts.length === 1) links[0] = { source: 0, target: 0, cycle: true };
      drawLinks(g, links.concat(pts.length === 2 ? [] : []), (j) => pts[j]);
    }
  }
  return svg;
}

function shadowSection() {
  const root = widget.shadowRoot;
  let style = root.querySelector("style.proto-style");
  if (!style) {
    style = document.createElement("style");
    style.className = "proto-style";
    style.textContent = SHADOW_TOKENS + STYLE;
    root.append(style);
  }
  const section = html("section", "proto");
  root.querySelector(".controls").after(section);
  return section;
}

function note() {
  return html("p", "note", `One dot is one simulated object, 16 real ones. <span class="swatch"></span>links on a cycle, which a drop leaves as cyclic garbage. +N: objects held beyond the sample.`);
}

// A: a strip of small diagrams, grouped by what holds each structure.
function variantA(name) {
  const preset = DATA[name];
  const section = shadowSection();
  section.append(html("h3", "", `Object graph of ${name}`), note());
  const strip = html("div", "strip");
  for (const [root, held] of [["module", "held by sys, a module's globals"], ["frame", "held by a frame"]]) {
    const members = preset.structures.filter((s) => s.root === root);
    if (!members.length) continue;
    const group = html("div", "group");
    group.append(html("div", "held", held));
    const row = html("div", "members");
    for (const s of members) {
      const figure = html("figure");
      figure.append(sampleSvg(s), caption(s));
      row.append(figure);
    }
    group.append(row);
    strip.append(group);
  }
  const churn = html("div", "group");
  churn.append(html("div", "held", "churn, held by frames briefly"));
  const figure = html("figure");
  figure.append(churnSvg(preset.churn), html("div", "caption", churnText(preset.churn)));
  churn.append(figure);
  strip.append(churn);
  section.append(strip);
}

// B: one force-directed diagram per preset, after its paragraph.
const OPENINGS = {
  create_gc_cycles: "create_gc_cycles, the first preset",
  json_loads: "json_loads models",
  xml_etree_parse: "xml_etree_parse models",
  async_tree_io_tg: "async_tree_io_tg models",
  connected_components: "connected_components models",
};

function variantB() {
  for (const [name, opening] of Object.entries(OPENINGS)) {
    const paragraph = [...document.querySelectorAll("main p")].find((p) => p.textContent.trim().startsWith(opening));
    if (!paragraph) continue;
    const section = html("figure", "proto proto-b");
    section.style.maxWidth = "70ch";
    section.append(html("h3", "", `Object graph of ${name}`), note());
    section.append(forceSvg(DATA[name]));
    const legend = html("div", "");
    legend.style.cssText = "display: grid; gap: 4px; margin-top: 6px;";
    DATA[name].structures.forEach((s, i) => {
      const line = html("div", "caption", `<span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--proto-s${i});margin-right:6px"></span><b>${s.label}</b>: ${shapeName(s)}, × ${s.size.toLocaleString("en")}, held by ${s.root === "module" ? "sys" : "a frame"}; ${timing(s)}`);
      line.style.maxWidth = "none";
      legend.append(line);
    });
    legend.append(html("div", "caption", `<b>churn</b>: ${churnText(DATA[name].churn)}`));
    section.append(legend);
    paragraph.after(section);
  }
}

function forceSvg(preset) {
  const width = 640, height = 340;
  const nodes = [{ key: "sys", kind: "root", label: "sys", fx: 40, fy: 30 }];
  const links = [];
  preset.structures.forEach((s, i) => {
    let holder = "sys";
    if (s.root === "frame") {
      holder = `frame${i}`;
      nodes.push({ key: holder, kind: "root", label: "frame", fy: 30 });
    }
    for (const n of s.nodes) nodes.push({ key: `${i}:${n.id}`, kind: "object", structure: i, head: n.id === 0 });
    links.push({ source: holder, target: `${i}:0`, cycle: false });
    for (const l of s.links) links.push({ source: `${i}:${l.source}`, target: `${i}:${l.target}`, cycle: l.cycle, self: l.source === l.target });
  });
  const real = links.filter((l) => !l.self);
  d3.forceSimulation(nodes)
    .force("link", d3.forceLink(real).id((d) => d.key).distance(16).strength(0.9))
    .force("charge", d3.forceManyBody().strength(-22))
    .force("collide", d3.forceCollide(5))
    .force("x", d3.forceX(width / 2).strength(0.04))
    .force("y", d3.forceY(height / 2).strength(0.06))
    .stop()
    .tick(400);
  for (const n of nodes) {
    n.x = Math.max(10, Math.min(width - 10, n.x));
    n.y = Math.max(10, Math.min(height - 10, n.y));
  }
  const svg = el("svg", { width: "100%", viewBox: `0 0 ${width} ${height}` });
  const byKey = new Map(nodes.map((n) => [n.key, n]));
  const g = el("g", {}, svg);
  const flat = links.map((l) => ({ source: l.source.key ?? l.source, target: l.target.key ?? l.target, cycle: l.cycle }));
  const held = flat.filter((l) => byKey.get(l.source).kind === "root");
  drawLinks(g, flat.filter((l) => !held.includes(l)), (key) => [byKey.get(key).x, byKey.get(key).y], 5);
  for (const l of held) {
    const s = byKey.get(l.source), t = byKey.get(l.target);
    el("line", { x1: s.x, y1: s.y, x2: t.x, y2: t.y, class: "link held-by" }, g);
  }
  for (const n of nodes) {
    if (n.kind === "root") {
      el("rect", { x: n.x - 16, y: n.y - 8, width: 32, height: 16, rx: 3, class: "root" }, svg);
      const t = el("text", { x: n.x, y: n.y + 3.5, "text-anchor": "middle", class: "rootlabel" }, svg);
      t.textContent = n.label;
    } else {
      el("circle", { cx: n.x, cy: n.y, r: n.head ? 4.4 : 3, style: `fill: var(--proto-s${n.structure})` }, svg);
    }
  }
  return svg;
}

// C: a row for each structure, its diagram beside its builds on the clock.
function variantC(name) {
  const preset = DATA[name];
  const section = shadowSection();
  section.append(html("h3", "", `Object graph of ${name}, on the allocation clock`), note());
  const rows = html("div", "rows");
  section.append(rows);
  const width = Math.max(240, section.getBoundingClientRect().width - 150 - 210 - 32 - 8);
  const x = d3.scaleLinear([0, preset.run_length / 1000], [0, width]);
  for (const [root, held] of [["module", "held by sys"], ["frame", "held by a frame"]]) {
    const members = preset.structures.filter((s) => s.root === root);
    if (!members.length) continue;
    rows.append(html("div", "rowhead", held));
    for (const s of members) {
      const glyph = sampleSvg(s, { gap: 14, spacing: 4, r: 1.6, more: false });
      glyph.setAttribute("width", Math.min(150, glyph.getAttribute("width")));
      glyph.setAttribute("preserveAspectRatio", "xMidYMid meet");
      rows.append(glyph, caption(s));
      const bars = el("svg", { width, height: 22 });
      for (const [first, last, drop] of s.spans) {
        el("rect", { x: x(first / 1000), y: 4, width: Math.max(0.6, x(last / 1000) - x(first / 1000)), height: 14, class: "build" }, bars);
        el("rect", { x: x(last / 1000), y: 4, width: Math.max(0, x(drop / 1000) - x(last / 1000)), height: 14, class: "alive" }, bars);
      }
      rows.append(bars);
    }
  }
  rows.append(html("div", "rowhead", "churn"));
  rows.append(churnSvg(preset.churn), html("div", "caption", churnText(preset.churn)));
  const band = el("svg", { width, height: 22 });
  el("rect", { x: 0, y: 4, width, height: 14, class: "churn" }, band);
  rows.append(band);
  rows.append(html("div"), html("div", "caption", "allocation clock (MB): solid while it builds, faint while it lives"));
  const axis = el("svg", { width, height: 22, class: "axis" });
  for (const tick of x.ticks(8)) {
    el("line", { x1: x(tick), x2: x(tick), y1: 0, y2: 5 }, axis);
    const t = el("text", { x: x(tick), y: 16, "text-anchor": "middle" }, axis);
    t.textContent = tick;
  }
  rows.append(axis);
}

function render() {
  for (const old of document.querySelectorAll(".proto-b")) old.remove();
  widget.shadowRoot?.querySelector("section.proto")?.remove();
  const name = entry();
  const v = variant();
  if (v === "B") variantB();
  else if (DATA[name]) (v === "C" ? variantC : variantA)(name);
  else if (name) {
    const section = shadowSection();
    section.append(html("p", "note", `${name} is no preset, so it has no object graph to draw.`));
  }
}

widget.addEventListener("entry", render);
addEventListener("prototype-variant", render);
render();
