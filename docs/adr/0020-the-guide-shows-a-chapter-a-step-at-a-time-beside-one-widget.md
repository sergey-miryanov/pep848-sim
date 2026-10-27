# The guide shows a chapter a step at a time beside one widget

The guide ran as an essay with eight widgets in it (#220). Each section spent
four or five paragraphs telling the reader which control to move and which
figure to read after, and a reader who read them scrolled back to the widget
to check. The guide shows one chapter at a time, as steps, beside one
widget that stays in place.

A step holds a sentence or two, the widget's request, and the panels and
figures it marks, each with a note on what to see there. `site/guide.json`
lists the chapters and their steps, and the tests read it. Each step is one of
the widget's entries, so the page steps by writing the entry's name into the
URL fragment, which the widget follows as it follows any entry's name. The
browser's Back button steps back, a link reaches a step, and the kept runs
(#135) draw a step the reader has seen at once. The controls stay live within
a step, and a chapter's steps share its controls.

A rail beside the widget holds the chapter, the arrows that step back and on
with the step's number between them, the step and its notes, then the
chapters, with the steps of the one shown. The arrows sit beside the
chapter's name, above the step's text, and the step's box keeps the height of
the guide's longest step, so nothing moves from one step to the next.

On a phone the rail stuck to the top and took 256 to 359 px of an 800 px
screen, and the widget's two columns stood 166 px wide each (#229). A phone
now shows the step, its notes and the first part it marks together:

- The rail docks at the foot of the screen with the chapter, the arrows, the
  step's title and its text. The box keeps its chapter's longest step's
  height, so the arrows move only between chapters. The page leaves room
  under the widget for the dock, and its scroll padding tells the widget how
  much of the screen the dock covers.
- The widget shows one collector at a time at the full width, through two
  tabs that stick to the top of the screen. Each tab carries the numbers of
  its collector's marks, and a step opens on the collector of the first panel
  it marks.
- Each note sits beside its badge in the widget: under a marked panel's
  title, or under the figures for a figure.
- On each new step the widget scrolls its first mark into view, unless it
  stands wholly in view already. A step that marks a figure and a panel
  leaves the second for the reader to scroll to: the figures stand about
  700 px above the panels.
- The settings start collapsed, and the chapters follow the widget.

At 1440 by 900 the widget stood 1,076 px tall under 240 px of heading and
intro, so its budget charts sat below the fold (#232). Beside the rail, the
guide now fits one window:

- The intro sits in a strip over the guide, which the reader closes once and
  the browser remembers. The page drops its heading.
- The widget's controls sit at the foot of the side, under the chapters, in a
  Settings block the reader collapses, which stays as they left it from step
  to step. Open, it keeps the height of the tallest chapter's controls, so a
  new chapter moves nothing above it. The chapters fill the side between the
  step and the settings, and scroll to keep the one shown in view.
- The widget's charts end at the window's foot: their plots scale alike, and
  their axes and legends stay.

The widget learns these things for the guide, so the page reaches nothing
inside its shadow root:

- A `compact` widget leaves out the object graph, its legend and the select,
  since the page picks the entry. With them, the charts fall below the fold
  and a step's text never sits beside the panel it talks about.
- An entry marks the panels and figures its page talks about, as
  `collector.panel` or `figure.name`. The widget outlines each with a badge
  that numbers it, in the order the entry lists them, and tints a marked
  figure's numbers. The entry can carry a note for each mark.
- A widget with a `changes` attribute notes under each figure what it read
  before the last runs it asked for, as soon as the new value shows, where
  the two differ. The note keeps its line while empty, so the charts stay put.
- A `fit` widget sizes its plots, between 0.3 and 1.3 of full size, so that
  it ends at the window's foot. The page sets it beside the rail alone.
- A `<gc-controls for="guide">` element on the page takes the widget's
  controls, with the widget's own styles, so the page places them without
  reaching into either shadow root.
- A `narrow` widget shows one collector at a time, which its tabs pick, shows
  each mark's note by its badge, and scrolls a new entry's first mark into
  view. The page sets it on a phone alone.

The chapters moved to steps one at a time. Until each moved, the guide linked
it to its section in a long form, the guide as it stood, where each section
embedded a widget of its own. The last chapter to move retired the long form
(#221 to #228).

Where the long form linked to the playground for a variant of a preset's
workload, such as async_tree_io_tg with parent pointers, a step runs the
variant in the guide's widget. A request that names a preset can carry
`changes`: each sets a field of the spelled-out request, by the path a control
names it with, and a path the request lacks is refused. The preset's numbers
stay in one place, and the step's request holds only what differs.

## Considered Options

A prototype on the `prototype/guide-steps` branch compared the rail with two
other layouts on the young generation's chapter, and with the full widget:

- The widget at full width and the step in a caption fixed over its foot: on a
  phone the caption covered half the screen.
- Step cards that scroll past a pinned widget, with no buttons: on a phone the
  cards covered the charts as they passed.
- The full widget beside the rail: the object graph pushed the charts below
  the fold in every layout.
- The page reaching into the widget's shadow root to mark parts, as the
  prototype did: it ties the page to the widget's markup.

A second prototype, on the `prototype/guide-fit` branch, compared three ways
to fit the widget in one window (#232):

- The intro and the settings in the rail, and charts at fixed, shorter
  heights: a window shorter than the one they were sized for cut them, and a
  taller one left room under them.
- The intro behind an About button, and only the panels a step marks at full
  height: the panels jumped from step to step, and the reader lost their
  place.
- The settings in the rail, under the step: the list of chapters jumped up
  and down with each chapter's controls.

A third prototype, on the `prototype/guide-phone` branch, compared three ways
to fit a phone (#229). The guide took the third, with the second's dock:

- The rail folded to its head, the title and two lines of text, with the
  columns fitted under it: the legends wrapped to three lines in 166 px
  columns, the plots fell to 0.3 of full size, and the clamped text hid part
  of the step.
- The step docked at the foot, with both columns side by side at full size:
  a heap panel only just fit above the dock, at 166 px wide.
- One collector at a time, with the notes in the widget and the rail on top.
