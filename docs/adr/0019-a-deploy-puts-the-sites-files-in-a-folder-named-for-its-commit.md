# A deploy puts the site's files in a folder named for its commit

GitHub Pages tells browsers to keep each file for 10 minutes
(`Cache-Control: max-age=600`), and the site can't change that. After #172
deployed, a browser kept the home page and the playground from the deploy
before, without the theme switch, and the widget's script, which ignored the
switch, while the stand-in page loaded fresh (#173). A page and its scripts
change together, and a browser that mixes two deploys can break either.

`just site` now puts the pages at the top of `_site/`, at the addresses they
had, and every other file, the scripts, the stylesheet, the worker and
`sim.zip`, into `v/<commit>/`, named for the first 12 digits of the commit it
assembles. It points each page's links to those files into the folder, and
leaves the links between pages alone. Inside the folder the modules import
each other, `runs.js` starts the worker and the worker fetches `sim.zip`, all
by relative URL, so each finds its own deploy's files without a change to the
scripts. A browser that cached a page loads the files that page was deployed
with, under names no other deploy uses.

A page that a browser cached before a deploy names the previous deploy's
folder. The deploy fetches the live `gh-pages` branch, and `just site --keep
FETCH_HEAD` copies the folder its home page names into `_site/`. The deploy
action clears every other folder, so `gh-pages` holds two deploys' files. Two
deploys inside 10 minutes would clear a folder that a page from the first
could still ask for, and we take that risk over keeping more.

`site/` stays as written, and `just serve` serves the assembled site, so work
on a page needs no build step. The presets page is the exception: `just site`
builds its `plot.json` into the folder (ADR 0021). A pull request's preview takes the same folder
under its own path, and each push replaces the preview whole.

The folder takes the commit's name, which tells which commit a page came from.
A deploy that changes no file of the site still makes browsers fetch its files
again, which costs little at the site's size.

## Considered Options

- The version as a query string on each page's links: it stops at the first
  import, so `gc-widget.js` would load the modules it imports from the cache,
  and a page from the deploy before would load the new scripts under its old
  query.
- An import map that names each module's versioned URL: a worker sees no
  import map, and a page from the deploy before would load the new scripts.
- A hash of each file in its own name: `just site` would rewrite every import
  in every script, a build step in all but name.
- A folder named for a hash of its files: a deploy that changed no file would
  keep its folder, but the name would no longer tell which commit a page came
  from.
- Every deploy's folder kept: `gh-pages` would grow by a deploy's files on
  every push to `main`.
