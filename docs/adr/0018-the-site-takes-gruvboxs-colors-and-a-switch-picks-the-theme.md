# The site takes gruvbox's colors, and a switch picks the theme

The site followed the system's color scheme with no way to change it, and took
its colors from the dataviz skill's reference palette (#170). The pages and the
widget now take gruvbox's colors, and a switch at the end of each page's nav
picks the light theme or the dark one.

A page starts in the system's scheme and follows it as it changes. Once the
reader presses the switch, the page keeps their choice in `localStorage`, so the
next page and the next visit open in it, and so does another open tab.
`theme.js`, a plain script in each page's head, sets `data-theme` on `<html>`
before the body paints, so a page never shows the other theme first.
`theme.css` holds every color once, for the pages and the widget: the
widget's shadow root inherits the custom properties. Plot takes each color as a
value when it draws, so the widget draws its charts again when `data-theme`
changes. Without JavaScript a page shows the light theme, and it can't run the
simulator either.

The text and the lines take gruvbox's medium background and its grays: fg1 for
text, fg2 for secondary text, fg4 for muted text and the axes, bg1 for the grid,
and bg3, or bg2 in the dark theme, for the zero lines. Each stands at about the
contrast the old colors had. The series take gruvbox's neutral accents, the row
its light and dark themes share: blue for the nursery, yellow for aging, aqua
for pending, orange for visited, purple for old, green for marked and red for
freed. Gruvbox has seven accents and the panels need eight. Survived shows in
both columns, and each accent names a series in one of them, so survived takes
a violet between gruvbox's blue and its purple.

Each series keeps its hue and moves only as far as the dataviz skill's
validator needs for its neighbors in each panel to pass, in both themes: the
heap's lanes, the incremental collector's old generation's stack, and the work
stack. In the light theme only the nursery moves more than a shade, to a
stronger teal, since gruvbox's blue reads as gray. In the dark theme gruvbox's
yellow sits above the validator's lightness band, and darkening it enough to
stay apart from pending turns it a mustard. Against the light theme's cream,
aging, pending and marked fall below 3:1, as aging did on the old palette. Each
panel's legend names them, as the validator asks of a color below 3:1.

## Considered Options

- Gruvbox's bright accents in the dark theme, as its editor themes use them:
  all but red sit above the validator's lightness band, and the blue reads as
  gray.
- Gruvbox's own yellow in the dark theme: aging would look like gruvbox and
  leave the validator's band.
- Survived in gruvbox's purple and old in another accent: every accent the
  legacy column doesn't use belongs to the incremental collector's spaces.
- A third state on the switch that goes back to the system's scheme: a menu or
  a third press, for a choice few readers want back.
- The colors in the widget, as before, and a copy of the surface and the text
  in each page: three copies to keep in step, and a widget that has to learn
  the page's theme anyway.
- The dark theme from a media query alone: a switch could override it only
  with a second copy of every dark color.
