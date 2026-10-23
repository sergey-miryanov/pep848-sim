// @ts-check
// What the widget's panels draw from a run's records: the heap by space, work in
// bins and where each y-scale ends. Also what each panel reads under the pointer.
// The module imports neither Plot nor the DOM, so Node's test runner can load it:
// see tests/panels.test.js.

/** @typedef {import("./runs.js").Record} Record */
/** @typedef {"legacy" | "incremental"} Collector */

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
// The fields of a record, by position.
export const CLOCK = 0, KIND = 1, MARKED = 2, WORK_TO_DO = 5;
const SPACES_BEFORE = 7, SPACES_AFTER = 8, REACHABLE_BEFORE = 9, REACHABLE_AFTER = 10;

// The kinds of a full collection's record: the workload's gc.collect() calls,
// and shutdown's two (ADR 0012).
export const FULL = ["full", "shutdown"];
// How opaque a full collection's work stands beside the runtime's own collections'.
export const FADED = 0.45;

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
 * Each bin's work, by the bin's index: marked, survived and freed by the
 * runtime's own collections, then by the full collections. A collection falls in
 * the bin of the kB it ran after: an automatic one ends the threshold0 kB it
 * covers, a full one the kB the workload called it in.
 * @param {Record[]} records
 * @param {number} binKb
 */
function bins(records, binKb) {
  /** @type {Map<number, number[]>} */
  const byBin = new Map();
  for (const record of records) {
    // A gc.collect() can come before the first allocation, at clock 0.
    const bin = Math.max(0, Math.floor((record[CLOCK] - 1) / binKb));
    const sums = byBin.get(bin) ?? [0, 0, 0, 0, 0, 0];
    const first = FULL.includes(/** @type {string} */ (record[KIND])) ? PARTS.length : 0;
    for (let part = 0; part < PARTS.length; part++) sums[first + part] += /** @type {number} */ (record[MARKED + part]);
    byBin.set(bin, sums);
  }
  return byBin;
}

/**
 * The work panel's data: each bin's work, stacked as marked, survived and freed,
 * the runtime's own collections' first and the full collections' faded above
 * them.
 * @param {Record[]} records
 * @param {number} binKb
 */
export function work(records, binKb) {
  return [...bins(records, binKb)].flatMap(([bin, sums]) => {
    const top = sums.findLastIndex((sum) => sum > 0);
    let y = 0;
    return sums.flatMap((sum, i) => {
      if (!sum) return [];
      const y1 = y;
      y += sum;
      const faded = i >= PARTS.length;
      return [{
        x1: (bin * binKb) / 1000, x2: ((bin + 1) * binKb) / 1000, y1, y2: y,
        part: PARTS[i % PARTS.length], opacity: faded ? FADED : 1, top: i === top,
      }];
    });
  });
}

/**
 * The records at the collection clock nearest `kb`, the earlier of two as near.
 * Several collections can share a clock, as shutdown's two do.
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
 * What the work panel reads under the pointer: the bin that holds `kb`, its
 * clocks in MB, and its work as the runtime's own collections and the full
 * collections did it, each as marked, survived and freed.
 * @param {Record[]} records
 * @param {number} binKb
 * @param {number} kb
 */
export function workAt(records, binKb, kb) {
  const bin = Math.max(0, Math.floor(kb / binKb));
  const sums = bins(records, binKb).get(bin) ?? [0, 0, 0, 0, 0, 0];
  return {
    x1: (bin * binKb) / 1000,
    x2: ((bin + 1) * binKb) / 1000,
    automatic: sums.slice(0, PARTS.length),
    full: sums.slice(PARTS.length),
  };
}
