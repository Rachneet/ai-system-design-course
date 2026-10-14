# Surface brief: course reader (scripts/template.html)

Scope: the whole reader (home, sheet index, lesson and lab sheets, library pages). Visitor mode: Read.
Audience and job: working engineers studying 40 to 60 minute lessons on a laptop over six weeks; they need to resume where they stopped, read comfortably, and check themselves.
Constraints: single static HTML artifact, Google Fonts only, light and dark, phone width, content and features listed in PRODUCT.md preserved.

## Direction contract

THESIS: The course is one engineer's computation pad for Relay: every lesson a numbered worksheet, every lab a worked problem with its result boxed. It refuses the docs-site arrangement (white page, blue links, card grid home).

OWN-WORLD: Pale-green computation paper (#e7efe3 family) with a faint 5 mm grid in the frame and margins only; near-white reading sheet; graphite ink for text, blue ballpoint for links and marks, one red margin rule reserved for "you are here" and the next action. Flat inks, hairline rules, no shadows or gradients. Worksheet header strips, ruled answer boxes, tick boxes, figure numbers.

STORY: The reader sees a pad with their place marked, opens the next sheet, reads in a calm column, sees numbers set as calculations, ticks the sheet done, and turns to the next.

FIRST VIEWPORT: Home: left margin holds the sheet index; the main area opens with the pad header (course name, sheets done of total, next sheet with a single red-ruled action), then the six weeks as sheet ranges listed as rows of numbered sheets with tick boxes. Lesson: worksheet header strip across the top (sheet no., week, time, status), title, lead, then the 66ch column; figures and the on-this-sheet index in the right margin.

FORM: Engineering computation pad, position 7 of my ordered list; seed key f28a5de2 (re-roll 1). Raises: fixed measure with margin navigation; state by mark shape not colour; nothing moves behind text; numbered figures; flat inks only.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
