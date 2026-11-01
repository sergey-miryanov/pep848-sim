# async_tree_io_tg's tasks take asyncio's shape

With the collector following the branch (ADR 0024), async_tree_io_tg's young
collections examined within 37% of its workers', and its old collections' work
within 25%. The preset's tree was a Hierarchy of 6 branches at 15 real objects
a task: 52,487 simulated objects for the benchmark's 55,987 tasks, about one a
task. An instrumented worker on the reference build shows how far that is from
what asyncio makes:

- sys reaches the tasks through the event loop, 7 references down. A walk from
  sys, first in, first out as the branch marks, scans 16,520 objects before the
  loop and 18,222 before its queue of handles ready to run.
- The ready queue holds a Handle for each task made and not yet run: 43,796 at
  the 30th collection, 15,825 at the 50th. The loop's heap of timers holds the
  sleeping leaves' TimerHandles, 30,831 at the 50th.
- The branch marks in layers of one type each, breadth first: the Handles at
  the 22nd collection, the Contexts and TaskStepMethWrappers at the 24th, the
  Tasks from the 26th to the 30th, then the coroutines and TaskGroups.
- A running task that starts a TaskGroup holds 13 tracked objects of its own,
  and a leaf 14. Its Handle and TaskStepMethWrapper go when the ready queue lets
  go of them, as the task first runs.
- Each task links back to its parent twice: its done-callback is a method of
  the parent's TaskGroup, which holds the parent in `_parent_task`, and the
  parent awaits it. The task also reaches itself through the Future it waits
  on and that Future's wake-up call. The tasks cut these links as they finish.

At one object a task, marking reached a whole task, with its six children, in
one step, and pulled the young objects into the old generation 16 times too
fast. The aging spaces ran empty, the young collections gave no budget, and
marking stalled.

A new shape, TaskGroups, builds the objects asyncio makes, in asyncio's order.
One simulated object stands for an object of one role in each of 16 tasks
that asyncio makes one after another (ADR 0002). A path of 10 objects leads
from the structure's root to the loop, which holds the ready queue and the
timers. A parent's step makes each group of 16 tasks with 7 objects: the task,
its coroutine, two Contexts, its Handle in the ready queue, the Handle's
TaskStepMethWrapper and the done-callback. When the group first runs, the
ready queue lets go of its Handle. A group of tasks with children then makes a
TaskGroup, its list and its set, its children's groups, and 5 objects to wait
on a Future. A group of leaves makes 9 objects, its timer and the timer's
arguments among them. The structure holds 55,429 objects, and a larger one
starts the tree again under the same loop.

A shape can now cut links before a drop: `teardown(size)` gives the pairs, and
`Build.drop` unlinks them before it lets go of the root. TaskGroups cuts each
task's links back to its parent and to itself, so a dropped tree leaves no
cyclic garbage, as on the reference build.

The tree now lives 10,000 kB after it has built, not 8,000. The workers' old
collection at 132 MB still marks 30,519 real objects of the first tree, and
their young collection at 134 MB finds 12,796 where the one before found
30,519. The build churn falls from 1.17 to 1.07 kB a kB of tree, which puts the
legacy gen 0 collections during a build at 15,488 real objects against the
workers' 15,260 to 15,600.

## Consequences

async_tree_io_tg's incremental columns on the presets page:

| Series | Before | After |
|---|---|---|
| gen 0 examined | 37% | 9% |
| gen 1 work | 25% | 10% |
| gen 1 budget | 12% | 3% |
| gen 1 examined | 4% | 4% |

Its legacy gen 0 examined falls from 3% to 2%, and gen 1 examined from 4% to
2%. Its legacy gen 1 yield stays at 16%. The workers' young collection at
134 MB finds 12,796 real objects, and the run's finds none. The other presets
keep their records.

The fit hangs on the tree's lifetime: below 10,000 kB, gen 0 examined comes
within about 20%, and at 10,500 or 11,000 kB within 12%.

The tree grows from 52,487 objects to 55,429, and its slider's largest from
59,300 kB to 62,200. The guide's chapters on the old generation and the work
budget take the new runs' numbers: 12 sweeps where there were 9, and old
collections that mark about 1,900 objects each. Without the freed credit, the
trees with parent pointers now go at 172, 324 and 500 MB, and the sweeps fall
from 10 to 6.

The playground and the request name the shape "task_groups", and a workload
source names it `TaskGroups()`.

## Amended: the Handle holds the task's Context

A walk from sys on the reference build, first in, first out, finds each young
Handle's Context one reference down, beside its TaskStepMethWrapper: the
workers' marking takes 20,582 Handles at the 22nd collection, then 16,836
Contexts and as many TaskStepMethWrappers at the 24th. `call_soon` runs the
task's step in the task's own Context, so the Handle holds it. The shape had
only the Task hold it, so marking reached the Contexts three references
later, with the coroutines and the done-callbacks, and took 37,000 young
objects at the 28th collection where the workers' took 7,000 (#290).

Each Handle now holds its task's first Context. The incremental collector's
sweeps end where the workers' end, at 100, 160, 192 and 228 MB, against 96,
160, 196 and 236 before. Summed over the run, the young collections examine
within 6% of the workers', against 14% before, and the old collections' work
comes within 10%, against 25%. The legacy collector's records stay the same.

## Considered Options

- Keep the Hierarchy and fit its lifetime and churn. Each object would still
  stand for a task and reach its six children, so marking would still pull the
  young objects 16 times too fast.
- Chains of tasks in groups of 16, without the ready queue, the timers and the
  links back. It reached 20% on gen 0 examined.
