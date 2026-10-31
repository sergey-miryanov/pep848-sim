# The incremental collector follows the reference branch

Supersedes ADR 0003.

ADR 0003 had the incremental collector follow the PEP's pseudocode where the
reference branch differs, so that the widget would explain the PEP as
published. A preset models a pyperformance worker, and gcmon records those
workers on the branch (ADR 0011). With the pseudocode, a preset could not fit
its worker's records, and no one could tell a preset's error from the
collector's. connected_components' workers take one increment of 231,870 real
objects at 60 MB, and the five young collections after it examine 6,600 to
13,600 each. The pseudocode's collector took its graph in three growing
increments and could not make that one.

The incremental collector now follows `Python/gc.c` on
`incremental-gc-update-2`, line by line where the simulator models the step:

- sys is tracked like any other object and starts in the nursery. The first
  old collection finds pending and reachable empty, swaps the spaces, and puts
  sys on reachable.
- Young objects carry old[0]'s tag. While visited is old[1], that is pending's
  tag, so in every other sweep marking and increments take young objects out
  of the nursery and the aging spaces.
- An old collection returns at once unless the budget is positive. It swaps
  the spaces first if pending and reachable are both empty. Then it marks from
  reachable's head and takes increments from pending's last object until it
  has done the budget's worth of work or both run empty. It settles the budget
  once: it debits what it marked and examined, and credits twice what its
  increments freed. If pending and reachable are empty at the end, it swaps
  the spaces and sets the budget to zero.
- Young collections and increments put their survivors at visited's front, and
  marking appends at its tail.
- A full collection leaves visited as old[1].

The collector keeps the pseudocode's names, and its docstring maps each to the
branch's field. ADR 0003's one exception stays: collections start with a young
one, as the PEP's abstract and the branch have it, where the pseudocode
starts with an old one (#259).

The guide still explains the PEP. Where the branch departs from the
pseudocode, as in the tag young objects carry, the guide says what the branch
does.

## Consequences

connected_components' young collections examine within 5% of its workers',
against 10% before, and its budget within 15%, against 17%. Its one increment
now comes at 56 MB and takes 295,696 real objects. The workers keep about 153
objects pending after theirs, so their budget sinks to -191,565, where the
simulator's empties pending, ends the sweep and sets the budget to zero.

async_tree_io_tg's young collections examine within 37% of its workers',
against 19%. sys reaches its task tree, so in the sweeps where young objects
carry pending's tag, marking takes every young task before a young collection
can examine it. The workers' young collections keep examining 7,500 to 30,000
real objects. Its preset needs part of each run held by frames, which sys does
not reach.

The legacy collector does not change.

## Considered Options

- Keep the pseudocode. A preset's error would mix the workload's shape with
  the collector's, and the presets page would keep a budget chart that differs
  from its benchmark's by design.
- Follow the branch but give young objects no tag. The sweeps would no longer
  alternate, and connected_components' one large increment would split into
  growing ones again.
