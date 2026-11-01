# A repeating structure can wait into the loops and skip while another builds

xml_etree_parse's young collections examined within 8% of its workers' under
the incremental collector. The workers' young collections find each value's
own tree at their 25th and 27th collections, split 1,130 and 4,029 real
objects, then at their 39th and 51st. The run's found it whole at the 25th,
37th and 49th, a young collection early each time.

A probe on the reference build logs where each of a worker's values builds its
tree, serialises it and parses, against the collections around them:

- A value builds its tree, 359 kB, serialises and writes it, 1,923 kB, parses
  60 times, 21,620 kB, then serialises the last two parsed trees as
  `bench_parse` returns, 1,920 kB. The workers' values run 25,826 kB, where
  the preset took 25,560.
- So each value's tree comes 1,920 kB after the last parse of the value before.
  The preset built it as the last parse ended.
- Serialising leaves 66 real objects alive besides the tree. The preset's
  serialising chains held about 1,000.
- The first value's tree starts at about 5,709 kB, after what pyperf allocates
  to start the benchmark. The preset started it as start-up ended, at 5,284.

The workload could not build that order. Every repeating structure first fell
due as the loops started, so nothing could follow a value's parses within the
value. A rebuild that fell due while another structure built waited for it, so
a parse due during the serialising would have come between it and the next
tree.

A repeating structure now takes two more parameters. Its `delay` is the kB
after the loops start that it first falls due; each rebuild after that comes
its interval later. With `skips_while_busy`, it skips a rebuild that falls due
while another structure builds or waits, where it would otherwise wait and
build once the other ends. A structure that builds once takes neither. Both
default to the old behaviour, and the other four presets keep their records.

xml_etree_parse's value takes 72 slots of 359 kB, 25,848 kB. The parsed trees
first fall due 2,410 kB into the loops and skip while the value serialises,
so each value parses 60. The serialising of the last two parsed trees falls
due as the 60th parse's tree ends. The serialising builds 4 simulated objects
and churn for the rest of its kB. A set-up of chains that go as they build
fills the 428 kB from start-up's end to the first tree, at 5,708 kB.

## Consequences

xml_etree_parse's columns on the presets page:

| Series | Before | After |
|---|---|---|
| incremental gen 0 examined | 8% | 1% |
| incremental gen 0 yield | 4% | 2% |
| incremental gen 0 budget | 1% | 0% |
| incremental gen 1 budget | 1% | 0% |
| legacy gen 0 examined | 4% | 4% |

The incremental young collections that find a value's tree examine 944, 4,208
and 5,152 real objects against the workers' 1,130, 4,029 and 5,158, at the
same collections. The gen 0 running yield stays within 4% of the workers' at
each young collection, and the budget within 1% at each collection.

Under the legacy collector, the gen 0 collections during each value's
serialising still differ: the workers' last two parsed trees stay alive until
`bench_parse` returns, and the run's go two slots after they build. The
workers' 39th collection examines 10,343 real objects there, the run's 64.
Since #285, the 59th and 60th parses build as structures of their own, which
fall due in those slots ahead of the other parses and go as the serialising
ends. The run's 39th collection examines 10,368.

The playground's editor shows both fields for each structure, the legend says
when a structure first falls due and that it skips, and a workload source
writes them as `delay=` and `skips_while_busy=True`. Links written before
leave them out and open at the defaults.

## Considered Options

- Serialise the last two parsed trees at the start of each value. The first
  value's tree would then start 1,920 kB after start-up, where the workers'
  starts about 430 kB after it.
- Make every repeating structure skip while another builds. async_tree_io_tg's
  runs change.
- Fit the value's length and the tree's churn alone. The tree still follows the
  last parse at once, so the young collection that finds it still comes early.
