# A reader's shape runs as Python in the page's worker

The playground lets a reader write a structure's shape (#155): Python that
defines `links(i)`, the links object i brings, as (source, target) pairs among
objects 0 to i. The request carries the code as `{"own": code}`, and the
simulator compiles it in the page's worker, under the Pyodide that runs
everything else. A reader's shape costs what a built-in shape costs: one call
for each object built.

The simulator checks every link the code gives before the heap makes it: two
ints from 0 to i, one of them from an earlier object that holds object i. An
object that nothing earlier holds would turn into garbage as soon as it was
built, and the heap counts uncollected garbage only at a drop. Before a run
starts, a request calls links(i) twice on each of a structure's first 1,024
objects. So most faults show as the reader leaves the box, with the line of
their code, and so does an answer that changes from one call to the next. The
simulator calls links(i) again to sample the object graph and to count the
cyclic garbage a drop leaves, and an answer that changes would draw one graph
and count another. A run depends only on its inputs (ADR 0007) as long as the
code does.

The workload's source (ADR 0015) gives a shape as a function by any name, and
the request carries its text alone. So the code may define one function in
place of links(i), and the simulator calls that. A message names the function
it called, and counts lines from where the code starts in the reader's text:
the box's first line, or the function's own line in the source.

A built-in shape declares the cyclic garbage a drop leaves. For a reader's
shape the simulator counts it by refcounting the structure's own links. The
drop takes away the first object's holder, refcounting frees each object left
without one, and what stays is the cyclic garbage. The simulator counts once
for each size and keeps the count. The object graph samples a reader's shape
four children to an object, up to 40 objects, so a list draws as long as a
tree.

The code runs in the worker, which has no page to change. It can fetch and
post messages, and the page reads what the worker posts as data. A link can
carry another reader's code, and it waits for the reader to press Run (ADR
0016). Code that never returns holds the worker. The Stop button
ends the worker and starts another (ADR 0009).

## Considered Options

- A class with parameters the editor shows as fields, as the built-in shapes
  have a width or a length: the reader would write more before seeing a graph,
  and the source view (#157) gives a shape its parameters as code.
- Counting a drop's cyclic garbage from the heap, by the objects still alive
  after it: it calls links(i) no second time, but the heap takes the count
  from the workload as it lets go, as a program knows what it built.
- CodeMirror for the box: it highlights and indents, at the cost of a bundle of
  modules from jsDelivr for one box. The textarea keeps a line's indent on
  Enter.
- A field for how many children and levels the sample keeps, as #155 first
  asked: a cap on the objects draws a list and a tree alike, with nothing to
  set.
