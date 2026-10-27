// @ts-check
// What the widget's panels draw from a run's records: the heap by space, work in
// bins and where each y-scale ends. Also what each panel reads under the pointer
// or where the keys take it, how a screen reader hears it, and how tall the
// panels stand.
// The module imports neither Plot nor the DOM, so Node's test runner can load it:
// see tests/panels.test.js.

/** @typedef {import("./runs.js").Record} Record */
/** @typedef {"legacy" | "incremental"} Collector */
/**
 * What a tooltip reads out: where, the unit over its quantities and each
 * column's head, then a row a quantity, with its name, its mark's color and a
 * value under each column.
 * @typedef {[string, string[], [string, string, string[]][]]} Readout
 */

// Each collector's spaces in the order its records hold them.
export const SPACES = {
  legacy: ["nursery", "aging", "old"],
  incremental: ["nursery", "aging", "pending", "visited"],
};
// The heap panel's lanes below the whole heap's, each with the spaces it stacks:
// the incremental collector's old generation is two.
export const LANES = {
  legacy: [["nursery"], ["aging"], ["old"]],
  incremental: [["nursery"], ["aging"], ["pending", "visited"]],
};
export const PARTS = ["marked", "survived", "freed"];

// The panels' heights in px at full size: a heap lane's plot, and the work and
// budget panels with their axes.
export const SIZES = { lane: 64, work: 160, budget: 130 };
// The axes' room above and below a panel's plot, and the room above and below
// each heap lane that neither axis takes.
export const AXES = { top: 16, bottom: 32 };
export const LANE_MARGIN = 12;
// How far a fitted widget scales its plots from full size (#232): below a third
// a lane is a line, and above 1.3 the bars outgrow what they say.
const LEAST = 0.3, MOST = 1.3;

/**
 * The heap panel's height: its lanes, the whole heap's among them, the room
 * between each two, and its axes.
 * @param {number} lanes
 * @param {number} lane
 */
export function heapHeight(lanes, lane) {
  return lanes * (lane + 2 * LANE_MARGIN) - 2 * LANE_MARGIN + AXES.top + AXES.bottom;
}

/**
 * The sizes that stack the heap, work and budget panels into a room of px: their
 * plots scale alike from full size, within LEAST and MOST, and their axes and
 * the room between lanes stay.
 * @param {number} room
 * @param {number} lanes
 * @returns {typeof SIZES}
 */
export function fitted(room, lanes) {
  const axes = AXES.top + AXES.bottom;
  const fixed = heapHeight(lanes, 0) + 2 * axes;
  const plots = lanes * SIZES.lane + SIZES.work - axes + SIZES.budget - axes;
  const scale = Math.min(MOST, Math.max(LEAST, (room - fixed) / plots));
  return {
    lane: Math.round(SIZES.lane * scale),
    work: axes + Math.round((SIZES.work - axes) * scale),
    budget: axes + Math.round((SIZES.budget - axes) * scale),
  };
}

/**
 * How many ticks a heap lane's axis takes: as many as its height has room for.
 * @param {number} lane
 */
export const laneTicks = (lane) => (lane < 30 ? 1 : lane < 40 ? 2 : 3);

// The fields of a record, by position.
export const CLOCK = 0, KIND = 1, MARKED = 2, WORK_TO_DO = 5;
const SPACES_BEFORE = 7, SPACES_AFTER = 8, REACHABLE_BEFORE = 9, REACHABLE_AFTER = 10;

// The kinds of a full collection's record: the workload's gc.collect() calls,
// and shutdown's three (ADR 0012).
export const FULL = ["full", "shutdown"];
// How opaque a full collection's work stands beside the runtime's own collections'.
export const FADED = 0.45;

// The keys that move a panel's reading, and which way: back, on, to the first,
// to the last. Up and down move it too, as on any slider.
const MOVES = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, Home: -Infinity, End: Infinity };
export const KEYS = Object.keys(MOVES);

// Each y-scale grows to the next of these times a power of ten (ADR 0008).
const STEPS = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];

/** The y-scale's end for data that reaches `value`, with room above it. */
export function ceiling(/** @type {number} */ value) {
  const room = value * 1.05;
  if (room <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(room));
  return STEPS.map((step) => step * power).find((end) => end >= room) ?? 10 * power;
}

/**
 * The heap panel's data: each record reads the heap before its collection and
 * after it, at the same clock (ADR 0010), so each lane rises between collections
 * and drops at each. The run starts from an empty heap. `whole` is the whole
 * heap and its reachable part, and `lanes` the bands each lane below it stacks.
 * @param {Collector} collector
 * @param {Record[]} records
 */
export function heap(collector, records) {
  const names = SPACES[collector];
  const points = [{ mb: 0, sizes: names.map(() => 0), reachable: 0 }];
  for (const record of records) {
    const mb = record[CLOCK] / 1000;
    points.push(
      { mb, sizes: record[SPACES_BEFORE], reachable: record[REACHABLE_BEFORE] / 1000 },
      { mb, sizes: record[SPACES_AFTER], reachable: record[REACHABLE_AFTER] / 1000 },
    );
  }
  const whole = points.map(({ mb, sizes, reachable }) => ({ mb, heap: sizes.reduce((sum, size) => sum + size, 0) / 1000, reachable }));
  const lanes = LANES[collector].map((spaces) => points.flatMap((point) => {
    let y = 0;
    return spaces.map((space) => {
      const y1 = y;
      y += point.sizes[names.indexOf(space)] / 1000;
      return { mb: point.mb, space, y1, y2: y };
    });
  }));
  return { whole, lanes };
}

/**
 * The bin that holds the kB a clock ends: an automatic collection's clock ends
 * the threshold0 kB it covers, a full one's the kB the workload called it in. A
 * gc.collect() can come before the first allocation, at clock 0.
 * @param {number} kb
 * @param {number} binKb
 */
const binOf = (kb, binKb) => Math.max(0, Math.floor((kb - 1) / binKb));

/**
 * Each bin's work, by the bin's index: marked, survived and freed by the
 * runtime's own collections, then by the full collections. A collection falls in
 * the bin of the kB it ran after.
 * @param {Record[]} records
 * @param {number} binKb
 */
function bins(records, binKb) {
  /** @type {Map<number, number[]>} */
  const byBin = new Map();
  for (const record of records) {
    const bin = binOf(record[CLOCK], binKb);
    const sums = byBin.get(bin) ?? [0, 0, 0, 0, 0, 0];
    const first = FULL.includes(/** @type {string} */ (record[KIND])) ? PARTS.length : 0;
    for (let part = 0; part < PARTS.length; part++) sums[first + part] += /** @type {number} */ (record[MARKED + part]);
    byBin.set(bin, sums);
  }
  return byBin;
}

/** A bin's whole work. */
const total = (/** @type {number[]} */ sums) => sums.reduce((sum, part) => sum + part, 0);

/**
 * Where the work panel's y-scale ends, over both columns' runs: past the most
 * work a bin holds without shutdown's. Shutdown takes the whole heap, and a
 * scale that fit it would leave the runtime's own bars slivers, so the panel
 * cuts its bin at the end instead. A run whose only work is shutdown's fits it.
 * @param {Record[][]} runs
 * @param {number} binKb
 */
export function workEnd(runs, binKb) {
  const most = (/** @type {(record: Record) => boolean} */ counts) =>
    Math.max(0, ...runs.flatMap((records) => [...bins(records.filter(counts), binKb).values()].map(total)));
  return ceiling(most((record) => record[KIND] !== "shutdown") || most(() => true));
}

/**
 * The work panel's data: each bin's work, stacked as marked, survived and freed,
 * the runtime's own collections' first and the full collections' faded above
 * them, up to the scale's `end`. A bin cut there gets no rounded top.
 * @param {Record[]} records
 * @param {number} binKb
 * @param {number} [end]
 */
export function work(records, binKb, end = Infinity) {
  return [...bins(records, binKb)].flatMap(([bin, sums]) => {
    const top = sums.findLastIndex((sum) => sum > 0);
    let y = 0;
    return sums.flatMap((sum, i) => {
      if (!sum || y >= end) return [];
      const y1 = y;
      y += sum;
      const faded = i >= PARTS.length;
      return [{
        x1: (bin * binKb) / 1000, x2: ((bin + 1) * binKb) / 1000, y1, y2: Math.min(y, end),
        part: PARTS[i % PARTS.length], opacity: faded ? FADED : 1, top: i === top && y <= end,
      }];
    });
  });
}

/**
 * The bins whose work runs past the scale's `end`, which the work panel cuts
 * there: each bin's clocks in MB and its whole work.
 * @param {Record[]} records
 * @param {number} binKb
 * @param {number} end
 */
export function cuts(records, binKb, end) {
  return [...bins(records, binKb)].flatMap(([bin, sums]) =>
    total(sums) > end ? [{ x1: (bin * binKb) / 1000, x2: ((bin + 1) * binKb) / 1000, work: total(sums) }] : []);
}

/**
 * The records at the collection clock nearest `kb`, the earlier of two as near.
 * Several collections can share a clock, as shutdown's three do.
 * @param {Record[]} records
 * @param {number} kb
 */
function nearest(records, kb) {
  let clock = -Infinity;
  for (const record of records) {
    if (Math.abs(record[CLOCK] - kb) < Math.abs(clock - kb)) clock = record[CLOCK];
  }
  return records.filter((record) => record[CLOCK] === clock);
}

/** The collections at one clock, by kind: "young collection", "2 shutdown collections". */
export function collections(/** @type {string[]} */ kinds) {
  /** @type {Map<string, number>} */
  const counts = new Map();
  for (const kind of kinds) counts.set(kind, (counts.get(kind) ?? 0) + 1);
  const names = [...counts].map(([kind, n]) => (n > 1 ? `${n} ${kind}` : kind));
  const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : names[0];
  return `${list} ${kinds.length > 1 ? "collections" : "collection"}`;
}

/**
 * What the heap panel reads under the pointer: the collections at the clock
 * nearest `kb`, and the heap before the first of them and after the last, in MB.
 * Null until the run's first record arrives.
 * @param {Record[]} records
 * @param {number} kb
 */
export function heapAt(records, kb) {
  const at = nearest(records, kb);
  if (!at.length) return null;
  const read = (/** @type {number[]} */ sizes, /** @type {number} */ reachable) => {
    const heap = sizes.reduce((sum, size) => sum + size, 0);
    return { heap: heap / 1000, reachable: reachable / 1000, garbage: (heap - reachable) / 1000, spaces: sizes.map((size) => size / 1000) };
  };
  const first = at[0], last = at[at.length - 1];
  return {
    clock: first[CLOCK],
    kinds: at.map((record) => record[KIND]),
    before: read(first[SPACES_BEFORE], first[REACHABLE_BEFORE]),
    after: read(last[SPACES_AFTER], last[REACHABLE_AFTER]),
  };
}

/**
 * What the work budget reads under the pointer: the collections at the clock
 * nearest `kb`, and the budget the last of them left. Null until the run's first
 * record arrives.
 * @param {Record[]} records
 * @param {number} kb
 */
export function budgetAt(records, kb) {
  const at = nearest(records, kb);
  if (!at.length) return null;
  return { clock: at[0][CLOCK], kinds: at.map((record) => record[KIND]), budget: at[at.length - 1][WORK_TO_DO] };
}

/**
 * What the work panel reads under the pointer: the bin that holds the kB `kb`
 * ends, so that a collection's clock reads the bin of its work, the bin's clocks
 * in MB, and its work as the runtime's own collections and the full collections
 * did it, each as marked, survived and freed.
 * @param {Record[]} records
 * @param {number} binKb
 * @param {number} kb
 */
export function workAt(records, binKb, kb) {
  const bin = binOf(kb, binKb);
  const sums = bins(records, binKb).get(bin) ?? [0, 0, 0, 0, 0, 0];
  return {
    x1: (bin * binKb) / 1000,
    x2: ((bin + 1) * binKb) / 1000,
    automatic: sums.slice(0, PARTS.length),
    full: sums.slice(PARTS.length),
  };
}

/**
 * Where a key moves a panel's reading from clock `kb`, in kB: the arrows to the
 * collection before or after, or on the work panel the bin before or after, and
 * Home and End to the first and the last. A bin reads at the clock that ends it,
 * where the collection that closes it ran. Null for any other key, and on the
 * heap or the budget before the run's first record.
 * @param {string} key
 * @param {number} kb
 * @param {string} panel
 * @param {Record[]} records
 * @param {number} binKb
 * @param {number} runLength
 * @returns {number | null}
 */
export function step(key, kb, panel, records, binKb, runLength) {
  if (!Object.hasOwn(MOVES, key)) return null;
  const stops = panel === "work"
    ? Array.from({ length: Math.ceil(runLength / binKb) }, (_, bin) => Math.min((bin + 1) * binKb, runLength))
    : [...new Set(records.map((record) => record[CLOCK]))];
  if (!stops.length) return null;
  // The stop the reading stands at: the bin that holds `kb`, or the nearest
  // collection, the earlier of two as near.
  const at = panel === "work"
    ? Math.min(binOf(kb, binKb), stops.length - 1)
    : stops.reduce((best, stop, i) => (Math.abs(stop - kb) < Math.abs(stops[best] - kb) ? i : best), 0);
  const to = at + MOVES[/** @type {keyof typeof MOVES} */ (key)];
  return stops[Math.min(Math.max(0, to), stops.length - 1)];
}

/**
 * What a screen reader hears of a tooltip's readout, as one sentence: "young
 * collection at 4 MB, in MB, before and after: heap 5.80, 5.20; reachable 3.00,
 * 2.80."
 * @param {Readout[0]} where
 * @param {Readout[1]} columns
 * @param {Readout[2]} rows
 */
export function spoken(where, [unit, ...heads], rows) {
  const columns = heads.length ? `${unit}, ${heads.join(" and ")}` : unit;
  return `${where}, in ${columns}: ${rows.map(([name, , values]) => `${name} ${values.join(", ")}`).join("; ")}.`;
}
