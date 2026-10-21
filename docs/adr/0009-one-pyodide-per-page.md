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

## Considered Options

- A worker per widget: the guide embeds one in every section, and each would
  pay the start, and on a cold cache the download, again.
- Starting Pyodide when the reader reaches the first widget: the reader
  would wait out the whole start there.
