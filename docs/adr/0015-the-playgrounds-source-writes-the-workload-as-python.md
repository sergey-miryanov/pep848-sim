# The playground's source writes the workload as Python

The playground's second editor, the workload source, shows the workload, the
run length and the collector settings as Python beside the widget (#157), the
prototype's third layout, and since #154 the collector constants and the real
object's size too. A switch beside the Workload select picks the legend's
editor (ADR 0013), the default, or the source. The source uses the
prototype's names: `Structure`, `Churn`, `Settings`, a class for each shape,
`Own` for a shape of the reader's own, and `Constants`. It sets `churn`,
`structures` and `run_length`, and may set `settings`, `constants`, `seed`
and `shutdown`. A reader can compute a size, build the structures in a loop,
or keep several shapes of their own in one place.

The source runs when the reader presses Run or Ctrl+Enter, not on each change
as the legend does, since half-typed Python fails at most keystrokes. The
request carries the text as `{"source": text, "every": n}`. The simulator runs
it in the page's worker, as it runs a shape of the reader's own (ADR 0014),
and the worker sends the request back spelled out, as it does for one that
names a preset. The page keeps the spelled-out workload, which the legend then
edits. A refusal or an error shows under the box, with its line where it has
one. The worker
reads each request four times, for its controls, its spelled-out form, its
object graph and its runs, and the parser keeps the last 16 it read. So the
source runs once for all four, and a source that draws random numbers still
makes one workload (ADR 0007).

The page writes the source from the request itself, in JavaScript, when the
reader switches to it. A request the simulator refused, after a change in the
legend, still gets a source, with the refused value in it. The page keeps the
reader's text while the reader changes nothing in the legend. Once they
change the request there, the page writes the source afresh, and a loop or a
computed size comes back as the values it made. A switch to the legend with
text that has not run runs it first. If it fails, the source stays, with its
error.

In the source, a shape of the reader's own is a function, and `Own` takes it.
The simulator carries the function's text alone into the request, from its def
to the last line of its body, so the legend's box shows the function as the
reader wrote it, under its own name. The function sees only i and what it
imports itself, as it would in the box. Messages count lines from where the
function starts in the source. Going back, the page writes each shape's code
as a function, renaming one whose name the source already uses. Code that
holds more than its function, such as a constant beside it, goes in as a
string, which `Own` takes too.

On a screen 1,200 px wide or more, the source sits beside the widget and
stays in view as the page scrolls, and the page widens to 1,520 px to keep
room for the panels. On a narrower screen it sits above the widget. The
writer wraps lines at 66 characters to fit the box. Two fixtures, a request
and its source, keep the writer and the reader in step: the JavaScript tests
write the one from the other, and the Python tests read it back.

## Considered Options

- The simulator writing the source, in the worker: Python would test the round
  trip with Hypothesis, but each switch would wait on the worker, and a request
  the simulator refused would have no source.
- The source and the spelled-out workload, both in the request, as the
  prototype carried them: each editor would hold its own workload, and a change
  in one would have to reach the other.
- `Own` taking the function itself, with the source's globals: shapes could
  share a helper, but the legend's box would get code that fails alone.
- CodeMirror for the box: ADR 0014's reasons hold, and the box keeps a line's
  indent on Enter as the shape's box does.
