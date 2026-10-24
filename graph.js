// @ts-check
// What the widget's object graph draws from a request's samples
// (pep848_sim.widget.graph): the nodes and links its layout places, how the
// layout fills its frame, and how the legend reads each structure, the churn and,
// on the playground, the run and the constants. The threshold controls take the
// young generation's sizes from here too.
// The module imports neither d3 nor the DOM, so Node's test runner can load it:
// see tests/graph.test.js.

/**
 * One structure as pep848_sim.widget.graph gives it: its shape as the legend
 * names it, its size, its root, its lifetime and rebuild interval in kB, whether
 * it calls gc.collect(), and its sample: each object by index with its level, and
 * each link with whether it lies on a cycle.
 * @typedef {{
 *   shape: string, size: number, root: "module" | "frame", lifetime: number | null,
 *   rebuild_interval: number | null, full_collections: boolean,
 *   objects: [number, number][], links: [number, number, boolean][],
 * }} Structure
 */
/**
 * The churn's parameters, its shares as fractions such as "1/50".
 * @typedef {{
 *   cycle_share: string, cycle_size: number, lifetime_mean: number,
 *   long_share: string, long_lifetimes: [number, number],
 * }} Churn
 */
/**
 * The collector constants and the real object's size, as
 * pep848_sim.collectors.collector.Constants holds them, the long-lived ratio as
 * a fraction such as "1/4".
 * @typedef {{
 *   initial_work_budget: number, freed_credit: number, long_lived_ratio: string,
 *   real_object_size: number,
 * }} Constants
 */
/** @typedef {{ structures: Structure[], churn: Churn }} Graph */
/**
 * A node the layout places: sys or a frame, or a sampled object of a structure,
 * its first or not.
 * @typedef {{ key: string, root?: "sys" | "frame", structure?: number, first?: boolean }} Node
 */
/**
 * A link between two nodes' keys: what a root holds, a link on no cycle, or one
 * on a cycle.
 * @typedef {{ source: string, target: string, kind: "held" | "link" | "cycle" }} Link
 */

/**
 * The nodes and links of a graph's samples. sys holds the structures a module
 * holds, and each structure a frame holds hangs from a frame of its own.
 * @param {Graph} graph
 */
export function network(graph) {
  /** @type {Node[]} */
  const nodes = [];
  /** @type {Link[]} */
  const links = [];
  const drawn = graph.structures.map((structure, i) => ({ structure, i })).filter(({ structure }) => structure.objects.length);
  if (drawn.some(({ structure }) => structure.root === "module")) nodes.push({ key: "sys", root: "sys" });
  for (const { structure, i } of drawn) {
    let holder = "sys";
    if (structure.root === "frame") {
      holder = `frame ${i}`;
      nodes.push({ key: holder, root: "frame" });
    }
    for (const [index] of structure.objects) nodes.push({ key: `${i}:${index}`, structure: i, first: index === 0 });
    links.push({ source: holder, target: `${i}:0`, kind: "held" });
    for (const [source, target, cycle] of structure.links) {
      links.push({ source: `${i}:${source}`, target: `${i}:${target}`, kind: cycle ? "cycle" : "link" });
    }
  }
  return { nodes, links };
}

/**
 * Where each placed node goes to fill a frame of that width and height less a
 * margin all round, the layout scaled the same both ways, never past `most`
 * times its own size, and centred.
 * @param {{ key: string, x: number, y: number }[]} placed
 * @param {number} width
 * @param {number} height
 * @param {number} margin
 * @param {number} most
 * @returns {Map<string, [number, number]>}
 */
export function fit(placed, width, height, margin, most) {
  const xs = placed.map(({ x }) => x), ys = placed.map(({ y }) => y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const scale = Math.min((width - 2 * margin) / Math.max(1, x1 - x0), (height - 2 * margin) / Math.max(1, y1 - y0), most);
  return new Map(placed.map(({ key, x, y }) => [key, [width / 2 + (x - (x0 + x1) / 2) * scale, height / 2 + (y - (y0 + y1) / 2) * scale]]));
}

/** kB as the legend reads them: 840 kB, 25.3 MB. */
const size = (/** @type {number} */ kb) =>
  kb < 1000 ? `${kb.toLocaleString("en")} kB` : `${(kb / 1000).toLocaleString("en", { maximumFractionDigits: 1 })} MB`;

/**
 * A structure as the legend reads it: its shape and size, what holds it, and
 * when the workload builds and drops it.
 * @param {Structure} structure
 */
export function describe(structure) {
  const { shape, root, lifetime, rebuild_interval: interval, full_collections: collects } = structure;
  const held = root === "module" ? "held by sys" : "held by a frame";
  let when;
  if (interval === null) {
    when = lifetime === null ? "built first, kept to the end" : `built first, dropped ${size(lifetime)} later`;
  } else {
    when = `rebuilt every ${size(interval)}, ${lifetime ? `each dropped ${size(lifetime)} later` : "each dropped as soon as built"}`;
    if (collects) when += ", gc.collect() before each build and after each drop";
  }
  return `${shape}, ${structure.size.toLocaleString("en")} objects, ${held}: ${when}`;
}

/** A share as a percentage, from a fraction such as "1/50". */
function percent(/** @type {string} */ share) {
  const [numerator, denominator = "1"] = share.split("/");
  return `${+((100 * Number(numerator)) / Number(denominator)).toFixed(1)}%`;
}

/**
 * The churn as the legend reads it: its lifetimes and the cycles it makes.
 * @param {Churn} churn
 */
export function describeChurn(churn) {
  const parts = [`objects that live about ${size(churn.lifetime_mean)}`];
  if (Number(churn.long_share.split("/")[0])) {
    parts.push(`${percent(churn.long_share)} living ${size(churn.long_lifetimes[0])} to ${size(churn.long_lifetimes[1])}`);
  }
  parts.push(Number(churn.cycle_share.split("/")[0]) ? `${percent(churn.cycle_share)} in cycles of ${churn.cycle_size}` : "no cycles");
  return `Churn: ${parts.join(", ")}`;
}

/**
 * The run as the playground's legend reads it: its length on the allocation
 * clock, the collector settings, and whether it ends in shutdown.
 * @param {{
 *   run_length: number, settings: { threshold0: number, threshold1: number, threshold2: number },
 *   workload: { shutdown: boolean },
 * }} request
 */
export function describeRun(request) {
  const { run_length: length, settings: { threshold0, threshold1, threshold2 }, workload: { shutdown } } = request;
  const end = shutdown ? ", then shutdown" : "";
  return `Run: ${size(length)} on the allocation clock, gc.set_threshold(${threshold0}, ${threshold1}, ${threshold2})${end}`;
}

/**
 * The incremental collector's young generation as threshold0 and threshold1
 * make it: a nursery of two half-spaces, threshold0 kB each, and threshold1
 * half-spaces of aging, held as threshold1 / 2 aging spaces, rounded up, each
 * the size of a nursery.
 * @param {number} threshold0
 * @param {number} threshold1
 */
export function describeYoung(threshold0, threshold1) {
  const spaces = Math.ceil(threshold1 / 2);
  return {
    nursery: `Incremental nursery: ${size(2 * threshold0)}`,
    aging: `Incremental aging: ${spaces} ${spaces === 1 ? "space" : "spaces"}, ${size(2 * threshold0 * spaces)}`,
  };
}

/**
 * The constants as the playground's legend reads them: the incremental
 * collector's work budget at the start and its credit for each object an
 * increment frees, the legacy collector's long-lived ratio, and the real
 * object's size.
 * @param {Constants} constants
 */
export function describeConstants(constants) {
  const { initial_work_budget: budget, freed_credit: credit, long_lived_ratio: ratio, real_object_size: bytes } = constants;
  return `Work budget from ${budget.toLocaleString("en")} real objects, plus ${credit} for each object freed, `
    + `a long-lived ratio of ${percent(ratio)}, ${bytes} B to a real object`;
}
