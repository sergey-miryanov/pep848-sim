# A widget's collector controls are shared and set apart from the workload's

The home page's widget gave each entry its own sliders, and only the stand-in
and json_loads offered threshold0 (#165). The thresholds belong to the
collector, not the workload, so a reader who switches entries should find them
on every one, in the same place. The widget's JSON now lists controls once
for every entry, beside the entries, and each entry lists its own workload
controls as before. The widget groups the controls by their path: the
workload's first, then the collector settings, `settings.*`, under their own
heading.

The collector settings show the three thresholds of `gc.set_threshold()`.
Under threshold0 and threshold1 the widget says what they make of the
incremental collector's young generation: a nursery of two half-spaces of
threshold0 kB, and threshold1 half-spaces of aging, as threshold1 / 2 aging
spaces rounded up. The sizes follow from the thresholds, as the PEP has them
(ADR 0003), so nothing new reaches the simulator. Only the legacy collector
reads threshold2, and its label says so; a reader who moves it sees the
incremental column stay as it was.

Under the settings, a toggle, closed at first, opens the collector constants,
`constants.*`: the initial work budget in real objects, the freed-credit
multiplier and the long-lived ratio. The home page lets a reader move them, as
the playground does (ADR 0013), so that the numbers the PEP fixes inside the
collector show what they change. The thresholds stay the widget's first view,
since Python can change them. A widget that offers no collector settings, as
the guide's section on the work budget does, shows the toggle open at first,
with no settings heading over it: there the constants are what the reader
came to move (#182). The real object's size stays on the playground:
it sets the simulator's scale, and moving it would change what every other
control's units mean (ADR 0002).

Each new control ranges about the PEP's value and widens to take in the
request's own: threshold1 from 1, which a widget's request needs, to 40;
threshold2 from 0 to 40; the initial work budget from -200,000 to 50,000 real
objects by the thousand; the multiplier from 0 to 10; the ratio from 0% to
100%.

## Considered Options

- The nursery's and the aging generation's sizes as controls of their own: a
  reader could size them apart from the thresholds, but the collector would no
  longer be the PEP's (ADR 0003).
- Each entry listing the collector's controls: six copies of one list, and an
  entry that left one out would lose it.
- The constants on the playground alone: the home page would show what Python
  can change and nothing of what the PEP fixes.
- The constants always open: ten sliders on the stand-in would push the
  figures a screen down.
