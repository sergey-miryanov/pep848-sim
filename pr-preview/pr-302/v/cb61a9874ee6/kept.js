// @ts-check
// The runs a widget keeps while the page stays open (#135): what the worker sent
// for the last requests whose runs finished, so that a request asked for again
// draws at once, with nothing asked of the worker.

/** @typedef {import("./runs.js").Record} Record */
/** @typedef {import("./runs.js").Figures} Figures */
/** @typedef {import("./runs.js").Control} Control */
/** @typedef {import("./graph.js").Graph} Graph */

/**
 * What the worker sent for one request whose runs both finished: the controls,
 * the request spelled out and a sample of its object graph, then each run's
 * records and its figures at the end.
 * @typedef {{
 *   controls: Control[],
 *   request: any,
 *   graph: Graph,
 *   records: { legacy: Record[], incremental: Record[] },
 *   figures: { legacy: Figures, incremental: Figures },
 * }} Runs
 */

// How many requests' runs a widget keeps. A preset's two runs come to at most
// about 250 kB as JSON, create_gc_cycles' at the shortest threshold0 its slider
// allows.
export const MOST = 16;

/** @param {number} a @param {number} b @returns {number} */
const gcd = (a, b) => (b ? gcd(b, a % b) : a);

/**
 * The key a request's runs go under, with the paths of the controls the widget
 * asked for, whose ranges the runs hold. The worker writes a share in lowest
 * terms, as "1/4", and the sliders and the legend in thousandths, as
 * "250/1000", so the key reduces each.
 * @param {any} request
 * @param {string[]} controls
 */
export function key(request, controls) {
  return JSON.stringify([request, controls], (_, value) => {
    const fraction = typeof value === "string" && /^(\d+)\/(\d+)$/.exec(value);
    if (!fraction) return value;
    const [numerator, denominator] = [Number(fraction[1]), Number(fraction[2])];
    const divisor = gcd(numerator, denominator) || 1;
    return denominator === divisor ? `${numerator / divisor}` : `${numerator / divisor}/${denominator / divisor}`;
  });
}

/**
 * The runs of a widget's last requests, at most `most` of them. The runs found
 * or kept longest ago go first.
 */
export class Kept {
  /** In the order the widget found or kept them, the latest last. */
  /** @type {Map<string, Runs>} */
  #runs = new Map();
  #most;

  constructor(most = MOST) {
    this.#most = most;
  }

  /**
   * The runs kept for the request and the controls, if any, which then go last.
   * @param {any} request
   * @param {string[]} controls
   * @returns {Runs | undefined}
   */
  find(request, controls) {
    const at = key(request, controls);
    const runs = this.#runs.get(at);
    if (runs) {
      this.#runs.delete(at);
      this.#runs.set(at, runs);
    }
    return runs;
  }

  /**
   * Keep the runs of the request and the controls, in place of any kept for
   * them before, and drop the oldest past `most`.
   * @param {any} request
   * @param {string[]} controls
   * @param {Runs} runs
   */
  keep(request, controls, runs) {
    const at = key(request, controls);
    this.#runs.delete(at);
    this.#runs.set(at, runs);
    for (const old of this.#runs.keys()) {
      if (this.#runs.size <= this.#most) break;
      this.#runs.delete(old);
    }
  }
}
