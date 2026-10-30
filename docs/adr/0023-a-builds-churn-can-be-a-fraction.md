# A build's churn can be a fraction

A build followed each object with a whole number of churn allocations. A
preset fits its build's length on the allocation clock from the records (ADR
0011), and a whole number moves that length a size at a time.
connected_components' graph holds 89,007 objects, so its load could take 89 MB
with no churn or 178 MB with one kB after each object. gcmon's records put it
at about 110 MB: while the graph loads, the workers' gen 0 collections examine
24,700 to 27,600 real objects each, of the 32,000 allocated since the last
one (#261). read_adjlist's lists, tuples and throwaway dicts come to about
0.24 kB for each kB of graph. With no churn, the preset's load ended 29 MB
early.

A structure's `build_churn` can now be a fraction. By its k-th object a build
has made k times the churn, rounded down, so a churn of 1/4 follows every
fourth object with one allocation and the others with none. A build then
takes its size plus its size times the churn, rounded down. A whole fraction
reads as an int. Every build of a structure spreads its churn the same way,
so a run still depends only on its inputs (ADR 0007).

A request holds a fractional churn as text, "6/25", as it holds a share, and a
whole one as a number, so a link from before still opens. A float in a request
is refused. The playground's editor shows the churn to a hundredth and writes
it back in hundredths, and the workload source writes the text.

## Considered Options

- Leave the churn out where it falls short of a kB an object. The load then
  ends 29 MB early, and the workers' collections stay busy for 63 of their 99
  collections where the run's stop at 47.
- Give the load a churn of 1 and a smaller graph. The graph's size comes from
  networkx's code, and a smaller one would hold fewer objects for the
  collections to examine once it has loaded.
- Draw each object's churn at random, with the fraction as its mean. The
  build's length would then vary with the seed, and a preset could not compute
  its run length from its structures.
