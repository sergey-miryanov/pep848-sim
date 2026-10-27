# A link carries the playground's request, and its code waits for Run

A reader who finds a workload worth showing sends its link (#156). After each
run the simulator takes, the playground writes the request into the URL
fragment, beside the name of the entry it belongs to, under the widget's id
and `.request`: `playground.request` on the playground. A button beside the
Edit switch copies the address. Opening the link, in this browser or another,
opens that entry with that request and runs it. A browser never sends a
fragment to the server, so the site's host never sees a reader's workload.

The link holds the request the worker spelled out, the one the legend edits:
the whole workload, the run length, the collector settings and the constants.
A link that named its preset and held only the fields the reader changed would
be shorter, but it would follow the preset's numbers when #117's rerun
changes them, and an old link would open runs its sender never saw. A whole
request opens the same runs for as long as the simulator stays the same (ADR
0007). The request goes in as JSON, compressed with deflate-raw by the
browser's `CompressionStream` and written in base64url. The stand-in's link
takes 435 characters where its JSON, escaped for a URL, takes 997. With the
doubly linked list the editor offers as a shape of the reader's own, the link
takes 676 and the JSON 1,595. The page refuses a link whose text opens to
more than 1 MB, or to anything but a request in that form.

A link holds the request, not the workload source's text. A reader who sends
a link from the workload source sends the workload their text made, and the
link opens a workload source written afresh from the request, without the
sender's loops and comments.

The simulator runs a shape's code as soon as it reads a request (ADR 0014),
in the page's worker, where Python can fetch from the site's origin and post
to the page. A link that ran its code on opening would let anyone who sends a
link run code on the site's origin. So a link whose request holds a shape of
the reader's own, or a shape that is not plainly a named one, opens in the
workload source with a note and waits for the reader to press Run. Until then
the switch to the legend stays shut, and picking another workload and coming
back waits again. The playground cannot tell a reader's own link from
another's, so a reload of a page whose address holds code waits too. The
workload source writes the request's other values as Python literals and the
names it knows, and refuses any other (#237), so a shape of the reader's own
is the only code a link can carry into it.

When the playground cannot open a link, it shows the entry as the page gives
it and says why. Picking another workload drops the link from the address
until that workload's runs write their own. Only a widget with the `editor`
attribute and an id writes a link, so the home page's address names its entry
alone.

## Considered Options

- Plain JSON in the fragment: no compression, but each quote and brace
  escapes to three characters, and a link more than doubles.
- The preset's name and the fields the reader changed: a shorter link that
  follows the preset's numbers when they change, as above.
- The workload source's text in the link: it keeps the sender's loops and
  comments, but a link would then come in two forms, and opening one would
  run more code than its shapes.
- A query string in place of the fragment: the server would receive every
  workload with each page load.
- Writing the address only when the reader presses Copy link: the address
  would go stale between copies, and a reload would lose the workload.
