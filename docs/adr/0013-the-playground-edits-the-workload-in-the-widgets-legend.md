# The playground edits the workload in the widget's legend

The playground lets a reader change any part of a workload: each structure,
the churn, the run length and the collector settings (#153). A prototype on
the `prototype/playground` branch put four editors around the real widget,
and the playground takes the fourth. The widget's legend, which names each
structure beside the object graph, becomes the editor. Each structure's
numbered line opens its fields under it: its shape and the shape's one
parameter, its size, what holds it, its lifetime, its rebuild interval, its
build's churn and its `gc.collect()` calls, with buttons that move it or
remove it. The churn's line and a line for the run open theirs, and a button
under the list adds a structure. A page asks for the editor with the widget's
`editor` attribute. The home page's widget keeps its legend and its sliders.

Each change runs both collectors again, as a control's release does, and the
charts keep the last runs until the new ones send their first records. A
change of a value leaves the fields in place, so the reader can tab on to the
next field while the runs start again. With each request the worker sends a
fresh sample of the object graph, and the structures' lines take their words
from it, the shapes' names included, so the names live in one place, the
Python. The editor words the churn's line and the run's line itself.

The browser checks each field against its least value before anything runs.
The simulator refuses the rest, such as a build that outlasts its rebuild
interval, and the playground shows its words under the field the reader
changed last, while the charts keep the last runs. It refuses every value
that would stop a run or crash it: a threshold0 under 1 kB loops forever, and
a structure of no objects never finishes its build. A threshold1 of 0 suits
the legacy collector but leaves the incremental collector no aging space, so
a widget's request refuses it.

The prototype's third layout, the workload as Python source beside the
widget, stays as a view the reader can switch to (#157).

## Considered Options

- A form beside the widget, run with a button: the narrow column wrapped the
  code of a shape of the reader's own (#155) and squeezed the widget's panels.
- A table of structures above the widget, with the churn and the run as
  sentences with fields in them: the widget kept its width, but the table
  pushed it a screen down.
- The workload as Python source beside the widget, from the start: a reader
  would learn the simulator's names before changing a single size.
- A Run button: several changes would make one run, but the playground would
  then work unlike the home page's sliders, and a reader would have to
  remember to press it.
