# One Pyodide per page, started when the page loads

The prototype for #7 timed the widget's start. From a page load to the first
chart took about 2.7 to 2.8 s with a cold browser cache and 1.3 to 1.5 s with
a warm one, and nearly all of it was Pyodide starting: 1.1 to 1.4 s of
compiling its WebAssembly and starting Python even with nothing to download,
and 6.2 MiB to download when the cache is cold. Once Python was ready, the
first chart was 80 to 115 ms away, and a run of 150 MB on the allocation
clock was done 0.4 to 0.5 s after that.

So a page makes one worker, and in it one Pyodide, as soon as it loads,
before the reader reaches any widget, and every widget on the page runs its
runs in that worker. A widget's re-run, after a control changes, never starts
Pyodide again: it costs the runs alone.

## Considered Options

- A worker per widget: the guide embeds one in every section, and each would
  pay the start, and on a cold cache the download, again.
- Starting Pyodide when the reader reaches the first widget: the reader
  would wait out the whole start there.
