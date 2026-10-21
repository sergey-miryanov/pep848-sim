# CLAUDE.md

- [`CONTRIBUTING.md`](CONTRIBUTING.md) is the process: Python version, setup,
  `just` recipes, checks, the site, publishing, pull requests. Follow it.
- [`CONTEXT.md`](CONTEXT.md) is the glossary. Use its terms and avoid the
  words it lists under _Avoid_. When a term settles or changes, update it in
  the same change. It holds vocabulary only, never implementation.
- [`docs/adr/`](docs/adr/) records decisions. Never contradict one silently:
  amend it, or ask.
- The incremental collector follows the PEP's pseudocode (ADR 0003) and the
  legacy collector follows the reference branch (ADR 0004). Do not "fix"
  either one toward the other.
