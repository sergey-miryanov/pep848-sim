# A record holds the heap before its collection and after it

Each collection leaves one record, and the record reads the heap twice: by
space and its reachable part, once before the collection runs and once after
it ends. The reference branch keeps the same pair for each collection,
`heap_size_start` and `heap_size_stop` in `struct gc_generation_stats`. Read
after each collection alone, the heap misleads the widget's charts. The
prototype for #9 found the nursery near zero in every such reading, since each
young collection empties it, and uncollected garbage peaks just before a
collection frees it, so ADR 0008's peak uncollected garbage would come out
low. Read before alone, the heap would hide what each collection left.

The record stays in ints and strings (ADR 0007). Each collector names the
spaces it reports, in the order a stacked chart draws them, and the
uncollected garbage is the heap less its reachable part.

## Considered Options

- After each collection alone: half the heap figures, with the nursery and
  the peak of uncollected garbage gone.
- Before each collection alone: the heap at its fullest, without what the
  collection left.
