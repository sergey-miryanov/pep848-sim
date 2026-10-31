# CLAUDE.md

- [`CONTRIBUTING.md`](CONTRIBUTING.md) is the process: Python version, setup,
  `just` recipes, checks, the site, publishing, pull requests. Follow it.
- Work from `gh issue list`. Link each pull request to its issue with
  `Closes #n`, or with `#n` alone when it does not finish the issue.
- [`CONTEXT.md`](CONTEXT.md) is the glossary. Use its terms and avoid the
  words it lists under _Avoid_. When a term settles or changes, update it in
  the same change. It holds vocabulary only, never implementation.
- [`docs/adr/`](docs/adr/) records decisions. Never contradict one silently:
  amend it, or ask.
- Run all prose through the `/stop-slop` skill before it lands, as
  _Prose_ in [`CONTRIBUTING.md`](CONTRIBUTING.md) says.
- Both collectors follow the reference branch: the incremental one (ADR
  0024) and the legacy one (ADR 0004). Do not "fix" either one toward the
  PEP's pseudocode.
