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

A rail beside the widget holds the chapter, Back and Next, the step and its
notes, then the chapters, with the steps of the one shown. Back and Next sit
above the step's text, and the step's box keeps the height of the chapter's
longest step, so neither moves from one step to the next. On a phone the rail
sticks to the top over the widget, and the chapters follow the widget (#229
fits the two together).

The widget learns three things for the guide, so the page reaches nothing
inside its shadow root:

- A `compact` widget leaves out the object graph, its legend and the select,
  since the page picks the entry. With them, the charts fall below the fold
  and a step's text never sits beside the panel it talks about. On a phone
  its two columns stay side by side.
- An entry marks the panels and figures its page talks about, as
  `collector.panel` or `figure.name`. The widget outlines each with a badge
  that numbers it, in the order the entry lists them, and tints a marked
  figure's numbers.
- A widget with a `changes` attribute notes under each figure what it read
  before the last runs it asked for, as soon as the new value shows, where
  the two differ. The note keeps its line while empty, so the charts stay put.

Until each chapter moves to steps, the guide links it to its section in the
long form, `site/guide-long.html`, the guide as it stood, where each section
embeds a widget of its own. The last chapter to move retires the long
form (#221 to #228).

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
