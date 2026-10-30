# A build in C holds back the runtime's collections until it ends

The reference branch takes each new real object's size off its budget, and
once the budget runs out it schedules a collection, which starts at the
interpreter's next check for pending work. Python code makes that check at
each call and each loop, and the simulator started each collection on the kB
it fell due (ADR 0011). C code that builds a structure makes no such check
until it returns. xml_etree_parse's workers parse with the C accelerator, and
gcmon's records show it (#269): while the workers parse, their collections
start 2,162 kB apart, six parses of 360 kB, and around the parses they start
2,000 kB apart. Each waits for the parse under way to return.

A structure can say C code builds it. While its build runs, the build's churn
included, the heap holds back an automatic collection that falls due, and
starts it with the first allocation after the build ends. The budget starts
again from there, so the next collection falls due `threshold0` kB after the
late one. A collection that falls due as the build starts runs before it, as
the interpreter checks before it calls the C code. `gc.collect()` and
shutdown's collections come when the workload calls them, as before. The
workload alone decides when a build runs, so both collectors' runs hold back
the same collections and still collect at the same boundaries (ADR 0005).

The playground's editor gives each structure a box for it, and the workload
source writes `built_in_c=True`. A link from before it leaves the field out
and opens as a structure Python code builds.

## Considered Options

- Start each collection on the kB it falls due. xml_etree_parse's preset could
  match its workers' 51 collections or the 108 MB they span, not both: kept
  2,000 kB apart, its collections miss one of the two by 6%.
- A threshold0 of 2,162 kB for xml_etree_parse. Every preset runs at the PEP's
  settings, and the widget's collector controls are shared between its
  workloads (ADR 0017). The workers' collections around the parses start
  2,000 kB apart.
- A fixed delay for each collection that falls due in a parse. Where the budget
  runs out in a parse moves from one collection to the next, and the records
  show each one starting as a parse ends.
