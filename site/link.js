// @ts-check
// The playground's link (ADR 0016): the page's address with the request the
// widget last ran in its URL fragment, so that it opens the same runs in another
// browser. The request goes in as JSON, compressed with deflate-raw and written
// in base64url; a fragment never reaches the server. Code in a request runs in
// the page, so a link that holds a shape of the reader's own waits for Run. The
// module needs no DOM, so Node's test runner can load it: see tests/link.test.js.

/** @typedef {import("./editor.js").Request} Request */

// The format a link's request is compressed in.
const FORMAT = "deflate-raw";
// The most bytes a link's request opens to, so that a link made to swell
// cannot fill the page's memory.
const LIMIT = 1 << 20;
// The fields of a request in the form the playground writes into a link, the
// one the worker spells out.
const FIELDS = ["workload", "settings", "run_length", "every", "constants"];
const DAMAGED = "The link is cut short or damaged: it opens no workload.";
export const FOREIGN = "The link holds no workload the playground wrote.";
const SWOLLEN = "The link opens to more than 1 MB, more than any workload the playground writes.";

/**
 * The request as a link's text.
 * @param {Request} request
 */
export async function encode(request) {
  const stream = new Blob([JSON.stringify(request)]).stream().pipeThrough(new CompressionStream(FORMAT));
  const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

/**
 * The request a link's text holds, refused unless it opens to a request in the
 * form the playground writes.
 * @param {string} text
 * @returns {Promise<Request>}
 */
export async function decode(text) {
  let request;
  try {
    const binary = atob(text.replaceAll("-", "+").replaceAll("_", "/"));
    request = JSON.parse(await inflated(Uint8Array.from(binary, (char) => char.charCodeAt(0))));
  } catch (error) {
    throw error instanceof Error && error.message === SWOLLEN ? error : new Error(DAMAGED);
  }
  const keys = request !== null && typeof request === "object" && !Array.isArray(request) ? Object.keys(request) : [];
  if (keys.length !== FIELDS.length || !FIELDS.every((field) => keys.includes(field))) {
    throw new Error(FOREIGN);
  }
  return request;
}

/**
 * Whether the request holds code: a shape of the reader's own, or a structure
 * whose shape is not plainly a named one. The simulator runs a shape's code as
 * soon as it reads the request, and Python in the page can reach the page, so a
 * link that holds code waits for the reader to read it and press Run.
 * @param {Request} request
 */
export function holdsCode(request) {
  const structures = /** @type {unknown} */ (request.workload?.structures);
  if (!Array.isArray(structures)) return true;
  return !structures.every((structure) => {
    const shape = structure?.shape;
    return typeof shape === "string" || (typeof shape === "object" && shape !== null && !Object.hasOwn(shape, "own"));
  });
}

/** The style of the button that copies a link, which the widget adds to its shadow root. */
export const LINK_STYLE = `
  .share { display: flex; align-items: center; gap: 8px; }
  .share button {
    font: inherit; color: var(--text-primary); background: var(--surface);
    border: 1px solid var(--baseline); border-radius: 4px; padding: 2px 8px; cursor: pointer;
  }
  .share button:disabled { color: var(--text-muted); cursor: default; }
`;

/**
 * The text that compressed bytes open to, refused past LIMIT.
 * @param {Uint8Array<ArrayBuffer>} bytes
 */
async function inflated(bytes) {
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream(FORMAT)).getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let text = "";
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > LIMIT) {
      await reader.cancel();
      throw new Error(SWOLLEN);
    }
    text += decoder.decode(value, { stream: true });
  }
  return text + decoder.decode();
}
