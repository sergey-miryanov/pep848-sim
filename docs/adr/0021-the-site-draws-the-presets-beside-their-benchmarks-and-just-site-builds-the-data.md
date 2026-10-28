# The site draws the presets beside their benchmarks, and `just site` builds the data

#256 drew each preset's collections beside its benchmark's workers on a dev
page in `tools/`, which shipped nowhere. The page found drift that the
averages `just compare` prints hide (#259 to #263), and a reader checking a
preset against its benchmark needs it as much as whoever fits one. The site
now serves it as the presets page, and each page's nav links it (#264).

The page draws from `plot.json`: each benchmark's 20 workers from the CSV files
in `data/`, and each preset's run under both collectors. `just site` runs the
presets and writes the file into the commit's folder beside the page's script
(ADR 0019), which fetches it by relative URL. A deploy and each pull request's
preview draw the presets as their own commit runs them, so the page never falls
behind the presets' code. The runs add about 10 seconds to each build.

The file holds a column per series and names each panel once: 1.3 MB, which
Pages sends gzipped as about 35 kB. `gh-pages` keeps two deploys' folders, so
two copies. The page runs no Pyodide and draws as soon as the file arrives.

This is the site's one build step. The presets page draws only from the
assembled site, under `just serve`. Every other page works from `site/` as
written.

## Considered Options

- `plot.json` committed to `site/`: builds stay fast, but the file falls behind
  each change to a preset unless a test runs the presets to compare, which
  costs `just check` the same seconds.
- The page runs the presets in Pyodide, as the widget does: it would ship the
  CSV files, 8.5 MB, and wait on ten runs in the browser.
- The page stays in `tools/`: only someone with a clone sees the drift.
