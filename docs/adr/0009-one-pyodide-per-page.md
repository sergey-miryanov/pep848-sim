# One Pyodide per page, started when the page loads

The prototype for #7 timed the widget's start. Getting from a page load to
the first chart took about 2.7 to 2.8 s with a cold browser cache and 1.3 to
1.5 s with a warm one. Pyodide starting took all of it but the last 80 to
115 ms: 1.1 to 1.4 s of compiling its WebAssembly and starting Python with
nothing to download, and 6.2 MiB to download when the cache is cold. A run of
150 MB on the allocation clock finished 0.4 to 0.5 s after the first chart.

A page makes one worker, and in it one Pyodide, as soon as it loads, before
the reader reaches any widget, and every widget on the page runs its runs in
that worker. A widget's re-run, after a reader changes a control, never
starts Pyodide again: it costs the runs alone.

A widget asks the worker for its runs once a reader comes within about a
screen of it (#177). The guide's long form embeds a widget in each of its
eight sections, and the worker takes every run it holds in turn, a part of
each (ADR 0006). A page that asked for every widget's runs on load would start
sixteen, and the section a reader is at would get one turn in eight. The guide
itself runs one widget, which steps through its chapters (ADR 0020). Pyodide
still starts with the page, so a widget the reader scrolls to waits only for
its own runs. Each chart takes the height it draws at before it draws, so a
widget that hasn't asked yet takes its full room, and the widgets below it
stay more than a screen away. A widget that the URL fragment names, by its
entry or its link, asks at once, and a widget the reader scrolls past keeps
the runs it started.

Python that never returns, as a reader's own shape can loop forever (ADR
0014), holds the worker and every widget's runs with it. The playground's Stop
button ends the worker and starts another, which starts Pyodide again, and
every request still running hears that its runs stopped.

## Considered Options

- A worker per widget: the long form embeds one in every section, and each would
  pay the start, and on a cold cache the download, again.
- Starting Pyodide when the reader reaches the first widget: the reader
  would wait out the whole start there.
- Every widget asking for its runs on load: the sections below would take
  turns from the section the reader is at.
- Interrupting Python in place, as Pyodide can, instead of ending the worker:
  it needs a SharedArrayBuffer, which needs headers GitHub Pages does not
  send.
