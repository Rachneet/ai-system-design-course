---
name: AI System Design
description: A free course reader set as a stack of numbered engineering worksheets, one sheet per lesson, on a plain high-contrast frame.
colors:
  pad: "#f2f3f5"
  pad-major: "#b9bec7"
  sheet: "#ffffff"
  box: "#f4f5f7"
  ink: "#111418"
  ink-2: "#474e5a"
  rule: "#d9dce2"
  pen: "#1f4f9c"
  pen-soft: "#dbe5f4"
  red: "#b8352a"
  code-str: "#1d6b3a"
  code-com: "#5f6672"
  code-num: "#8a4b12"
  pad-dark: "#0d0f12"
  pad-major-dark: "#4a505b"
  sheet-dark: "#16181c"
  box-dark: "#1e2126"
  ink-dark: "#eceef1"
  ink-2-dark: "#b0b6c0"
  rule-dark: "#2e323a"
  pen-dark: "#93b4ef"
  pen-soft-dark: "#22324c"
  red-dark: "#f07a6a"
  code-str-dark: "#9fd3a8"
  code-com-dark: "#8a919c"
  code-num-dark: "#e3b07a"
  vz-compute: "#2a5db0"
  vz-memory: "#6c4aa6"
  vz-good: "#23784a"
  vz-warn: "#a8650f"
  vz-bad: "#b3362b"
  vz-compute-dark: "#8db2f2"
  vz-memory-dark: "#c0a6f0"
  vz-good-dark: "#7fcf9f"
  vz-warn-dark: "#e8b464"
  vz-bad-dark: "#f08a7e"
typography:
  display:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "clamp(36px, 4.4vw, 60px)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "clamp(34px, 4.4vw, 52px)"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.02em"
  numeral:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "40px"
    fontWeight: 700
    lineHeight: 1
  numeral-compact:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1
  title:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.01em"
  title-week:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "25px"
    fontWeight: 700
    lineHeight: 1.12
  title-sm:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "21px"
    fontWeight: 700
    lineHeight: 1.12
  lede:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "20.5px"
    fontWeight: 400
    lineHeight: 1.55
  body:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.68
  body-compact:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.68
  blurb:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "16.5px"
    fontWeight: 400
    lineHeight: 1.68
  worked:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "16.5px"
    fontWeight: 400
    lineHeight: 1.6
    fontFeature: "tnum"
  option:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.45
  ui:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.35
  label:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: 1.35
  field-label:
    fontFamily: "Source Sans 3, Source Sans Pro, Helvetica Neue, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    letterSpacing: "0.02em"
  number:
    fontFamily: "Source Code Pro, ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 600
    fontFeature: "tnum"
  code:
    fontFamily: "Source Code Pro, ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: "13.5px"
    fontWeight: 400
    lineHeight: 1.6
  hand:
    fontFamily: "Kalam, Comic Neue, Segoe Print, cursive"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.3
  hand-title:
    fontFamily: "Kalam, Comic Neue, Segoe Print, cursive"
    fontSize: "17px"
    fontWeight: 700
  hand-big:
    fontFamily: "Kalam, Comic Neue, Segoe Print, cursive"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.1
rounded:
  none: "0px"
  focus: "2px"
spacing:
  rail: "304px"
  measure: "980px"
  gutter: "56px"
  frame: "28px"
  sheet-inset: "44px 48px 56px"
components:
  button-primary:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.ui}"
    rounded: "{rounded.none}"
    padding: "12px 18px"
  button-primary-hover:
    backgroundColor: "{colors.pen-soft}"
    textColor: "{colors.ink}"
  button-mark:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.ui}"
    rounded: "{rounded.none}"
    padding: "9px 14px"
  button-mark-hover:
    backgroundColor: "{colors.pen-soft}"
  button-tool:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "6px 10px"
  button-tool-hover:
    backgroundColor: "{colors.box}"
  input-search:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "9px 11px"
  header-strip-cell:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.ui}"
    padding: "8px 14px"
  callout:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "14px 18px"
  callout-numbers:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    typography: "{typography.worked}"
    rounded: "{rounded.none}"
    padding: "14px 18px"
  code-block:
    backgroundColor: "{colors.box}"
    textColor: "{colors.ink}"
    typography: "{typography.code}"
    rounded: "{rounded.none}"
    padding: "16px 18px"
  figure-frame:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.none}"
    padding: "18px"
  quiz-option:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.option}"
    padding: "8px 10px"
  quiz-option-hover:
    backgroundColor: "{colors.box}"
  tick-box:
    backgroundColor: "{colors.sheet}"
    size: "14px"
  nav-item:
    textColor: "{colors.ink}"
    padding: "6px 6px 6px 2px"
  nav-item-current:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
---

# Design System: AI System Design

## Overview

**Creative North Star: "The Worksheet"**

Each lesson is one numbered engineering worksheet: a white sheet outlined in near-black ink, opened by a ruled header strip, and read in a calm serif column. The sheets sit on a plain, quiet neutral frame (the index rail and the outer margin) that recedes so the sheet reads first. Everything on the sheet is drawn the way a careful engineer would draw it by hand: hairline rules, tick boxes, boxed answers, numbered figures, blue pen for links and marks, and a single red mark for where you are and what comes next.

Legibility comes before atmosphere. Text sits on flat, untextured surfaces at high contrast: near-black ink on white for reading, and a dark secondary gray that still clears AA comfortably on the sheet, the frame, and the answer boxes. Nothing patterned, gradiented, or tinted ever sits behind text. This holds everywhere, including the worked-numbers callout.

Density is moderate and steady. The reading column is fixed, the furniture around it is compact and set in a narrow grotesque, and numbers are set in mono or tabular figures so tallies line up. Surfaces are flat inks on paper, separated by rules rather than by depth.

**Key Characteristics:**
- A plain neutral frame and a white sheet; no textures anywhere.
- Near-black ink, blue ballpoint for links and marks, one reserved red.
- Square corners and 1px rules everywhere; state shown by mark shape.
- Source Sans 3 (Coursera's typeface) for structure and reading, Source Code Pro for numbers and code, Kalam only inside diagrams.
- Numbered sheets and numbered figures; the lesson outline in the index rail.

## Colors

A cool, near-neutral palette with near-black ink, one blue pen, and one red reserved for position.

### Primary
- **Ballpoint Blue** (pen): links, focus rings, drawn tick marks, the correct-answer outline in quizzes, and keyword colour in code. It is the hand that marks the paper.
- **Pale Ballpoint Wash** (pen-soft): text selection and the hover fill on pressable controls (primary action, check-this-sheet, copy).

### Secondary
- **Margin Red** (red): reserved for "you are here" and the single next action. It appears as the current sheet number and its underline in the index, the next-up sheet number on home, the underline on the Next link in the pad strip and the pager, the 3px underside rule of the primary action, and the text caret in inputs.

### Neutral
- **Quiet Frame** (pad): the plain page background behind every sheet and the index rail.
- **Frame Line** (pad-major): the default thin scrollbar thumb.
- **White Sheet** (sheet): the worksheet surface, header strip, buttons, search field, figure frames, and every callout.
- **Answer Box** (box): code blocks, inline code, table headers, quiz header, sign-off strip, and quiet hover fills.
- **Ink** (ink): body text, headings, sheet outlines, and every structural 1px border.
- **Secondary Ink** (ink-2): secondary text, ledes, field labels, figure captions, mono numbers, and the code block border. It is deliberately dark (about 8:1 on the sheet, 7.5:1 on the frame).
- **Hairline** (rule): internal dividers inside strips, tables, lists, and quizzes, and the rail's edge against the frame.
- **Code inks** (code-str, code-com, code-num): string, comment, and number/title colours for highlighted code; keywords reuse Ballpoint Blue.

### Dark theme
Dark mode swaps every token in place for neutral grays (the `*-dark` tokens): a near-black frame, a dark gray sheet, a slightly lighter answer box, off-white ink, light gray secondary ink, a lightened pen and a lightened red. It follows the system setting unless the reader picks light or dark explicitly. Contrast holds in dark too (ink about 15:1, secondary ink about 8.7:1 on the sheet).

### Named Rules
**The Clear Ground Rule.** Text always sits on a flat, solid surface at high contrast. No grids, patterns, gradients, tints, or images behind text, on the frame, the sheet, or any callout. Body text stays near-black on white; secondary text never drops below the Secondary Ink value.

**The One Red Rule.** Red marks position and the next step, nothing else. Never use it for errors, emphasis, decoration, or a second action on the same screen.

**The Ink Structure Rule.** Structural edges (sheet, strip, table, figure, callout, quiz, pager) are Ink; dividers inside them are Hairline. Colour never separates surfaces on its own.

## Typography

**Display Font:** Source Sans 3, the open successor of Source Sans Pro, Coursera's brand typeface (with Helvetica Neue, Arial)
**Body Font:** Source Sans 3 at 18px, 1.6 line height
**Label/Mono Font:** Source Code Pro (with ui-monospace, SF Mono, Menlo, Consolas)

**Character:** A condensed, heavy engineering grotesque does the labelling and structure, the way a worksheet's printed furniture would; a warm book serif carries the long reading. Mono is reserved for anything counted.

### Hierarchy
- **Display** (800, clamp(36px, 4.4vw, 60px), 1, width 72%): the home cover statement only, capped at 24ch and balanced.
- **Headline** (800, clamp(34px, 4.4vw, 52px), 1.12, width 82%): the sheet title at the top of each lesson.
- **Numeral** (800, 40px, 1, width 70%): week labels in the home sheet list.
- **Numeral Compact** (800, 30px): the same week label, inline, at phone width.
- **Title** (750, 28px, width 88%): lesson section headings, each opened by a full-width Ink rule above it.
- **Week Title** (750, 25px, width 86%): home week titles and the Library heading.
- **Title Small** (700, 21px, width 92%): subsections.
- **Lede** (400, 20.5px, 1.55): the summary under a title, in Secondary Ink; 21px at 54ch on home.
- **Body** (400, 18px, 1.68): reading text across the full lesson width (up to 980px).
- **Body Compact** (17px): body at phone width; also the size of minor headings (h4) and Library entry titles.
- **Blurb** (Source Sans 3 400, 16.5px): the week blurb under each home week title, at 62ch in Secondary Ink.
- **Worked** (Source Sans 3 400, 16.5px, 1.6, tabular): the text of the worked-numbers callout.
- **Option** (Source Sans 3 400, 16px, 1.45): quiz answer options. The primary action's label uses 16px Source Sans 3 700.
- **UI** (600, 15px): header strip values, buttons, tables, sign-off text.
- **Label** (700, 13px): callout labels, table headers, figure captions.
- **Field Label** (400, 11px, 0.02em): the small name above each header strip value, in sentence case.
- **Number** (mono 600, 12px, tabular): sheet numbers, counts, tallies, figure numbers.
- **Code** (mono 400, 13.5px, 1.6): code blocks.

### Named Rules
**The Counted Things Rule.** Anything counted (sheet numbers, tallies, scores, worked numbers, figure numbers) is set in mono or with tabular figures, zero padded to two digits where it is a sheet number.

**The One Family Rule.** Source Sans 3 carries headings, interface and reading text; weight and size make the hierarchy, not a second family. Mono is for code and counted numbers; the hand font is for diagrams only.

## Layout

The app is a two-column grid: a sticky 304px index rail on the quiet frame, edged by a Hairline, then the main frame with 28px of breathing room around a single sheet capped at 1120px. Inside a lesson sheet there is one column, up to 980px wide, with 44px 48px 56px of inset. Everything, prose included, uses the full lesson width; the owner prefers text that aligns with the figures and code over a narrow reading column. The lesson outline lives in the index rail, nested under the current lesson as a hairline-edged list of its sections; the section in view is marked in ink with a Ballpoint Blue tick, and the rail scrolls itself to keep the current lesson visible. There is no right margin.

Home uses the same sheet with a pad header strip (Pad, Checked, Next, Total), the cover statement and lede, one primary action, then the weeks as rows: a 120px numeral column beside the week title, blurb, and an auto-filling list of numbered sheets (min 230px per column).

Responsive steps: at 900px and below the rail becomes an off-canvas drawer (min(88vw, 340px)) behind an "Index" button in a sticky top bar on the sheet colour, is visibility-hidden when closed so it cannot take focus, and the sheet goes full bleed with only its bottom edge drawn. Body steps down to 17px and week numerals to 30px inline. Header strips reflow to four, or two, equal cells. Safe-area insets are respected on every edge.

**The Full Width Rule.** Prose, figures, tables and code share one edge at the full lesson width (capped at 980px), so nothing floats in a narrower column.

## Elevation & Depth

The system is flat. Depth is conveyed only by a white sheet sitting on the quiet frame and by drawing edges with 1px Ink lines. There is no cast shadow vocabulary. Inset box shadows appear only as drawn rules: the 3px red underside of the primary action and the inner second line of the design rule callout. The scrim behind the open phone drawer is a flat translucent wash.

**The Paper Not Glass Rule.** Surfaces sit on the page; they do not hover above it. Use a rule, a fill change to Answer Box, or a heavier border to separate, never a blur shadow, gradient fill, or translucency on content.

## Shapes

Every container is square: zero radius on sheets, buttons, inputs, callouts, code, tables, and figures. The only round forms are marks: the hollow circle that labels a tip and the 2px softening on the focus outline. Borders are 1px by default; 1.5px is reserved for things the reader presses or ticks (the primary action, check-this-sheet button, tick boxes, boxed worked numbers) and for the open drawer's edge. A dashed border marks the design review question callout; a dotted Hairline separates sheet rows on home.

**The Mark Shape Rule.** State and type are told apart by shape, never colour alone: a drawn tick for done, a struck cross and strikethrough for a wrong answer, and a distinct drawn shape (solid square, triangle, hollow circle, short dash, double bar) before each callout label.

## Components

### Sketch figures and calculators
- **Sketch figure** (`viz` block): HTML lays out panels, chips, bars, cell grids and arrows so the figure reflows on phones; rough.js then draws hand-drawn outlines and hatched fills over it, seeded so the drawing is identical on every load. Labels are Kalam (hand). Lesson text never uses the hand font.
- **Diagram inks:** one meaning each, in every figure: compute or prefill (vz-compute, blue), memory or decode (vz-memory, violet), a win (vz-good, green), a cost (vz-warn, amber), waste or failure (vz-bad, red, cross-hatched when it is pure waste). Chips with text get a solid 15% tint, never hatching behind words.
- **Mermaid flowcharts** use Mermaid's hand-drawn look in the same font and inks, rendered after the font loads so labels are measured correctly.
- **Calculators** (`widget` block): a bordered box with an Answer Box header, numeric inputs in mono, results as bordered cells (green when a target is met, red when not), one meter, and a one-paragraph explanation of the formula.
- Every figure carries a numbered caption, and every number in it links to its source under the drawing.

### Buttons
- **Shape:** square (0px), Ink border.
- **Primary (the next action):** ink on sheet with a 1.5px Ink border and a 3px Margin Red rule along its underside, 16px/700 Source Sans 3, 12px 18px padding. One per screen, on home only. Hover fills with Pale Ballpoint Wash; active presses down 1px.
- **Check this sheet:** the same ink-on-sheet form without the red rule, carrying a tick box before its label; pressed state is announced with aria-pressed and the tick draws in over 420ms.
- **Tool:** compact 1px bordered sheet buttons (Theme, Clear ticks, Index, Copy) at 12 to 12.5px/600; hover fills with Answer Box. Destructive tools arm on first click and confirm on the second.

### Chips
- **Lab tag:** lowercase mono "lab" at 10.5px inside a 1px Secondary Ink box, set after a sheet title.

### Cards / Containers
- **Sheet:** White Sheet fill, 1px Ink outline, square, opened by a header strip of ruled cells (field label over value), cells divided by Hairlines and the strip closed by an Ink rule.
- **Callouts:** five types, all on plain White Sheet, 1px Ink border, 14px 18px padding, capped at the measure plus 40px. Design rule adds an inner second line; watch out uses a triangle mark; tip a hollow circle; design review question a dashed border and short dash mark; worked numbers uses a Secondary Ink border, Worked type, a double-bar mark, and each result boxed in mono with a 1.5px Ink border. No callout carries a texture.
- **Sign-off strip:** Answer Box fill with the check button and a one-line instruction.
- **Pager:** two Ink-ruled cells; the Next title is underlined in Margin Red.

### Inputs / Fields
- **Search:** square, 1px Ink border on White Sheet, 15px Source Sans 3, red caret; focus draws the 2px Ballpoint Blue outline at a 2px offset. "/" focuses it from anywhere.

### Navigation
- **Index rail:** grouped by week under an Ink-ruled group head with a mono count. Each row is a tick box, a mono sheet number, and the title. Hover lays a 70% sheet wash; the current sheet sits on White Sheet with its number in Margin Red and its title underlined in red. The rail scrollbar has a solid sheet track and a Secondary Ink thumb so position is easy to read.
- **Margin index:** numbered section links and a numbered "Figures" list that scroll smoothly to their target.

### Figures
- Numbered like plates ("Fig. 3.2" for the second figure on sheet 03), framed in 1px Ink on White Sheet, drawn in the sheet's own inks (diagram nodes on sheet, lines in Secondary Ink, clusters on Answer Box). Wide figures keep at least 80% of their natural width and scroll sideways rather than shrink, with a visible scrollbar and a caption hint "Scroll sideways for the full figure."

### Quiz
- An Ink-bordered box with an Answer Box header ("Check yourself" and a mono score). Options are Option-type rows with a tick box; after answering, the correct option gains a Ballpoint Blue outline and a drawn tick, a wrong pick is crossed and struck through, and a short explanation follows in Secondary Ink.

## Do's and Don'ts

### Do:
- **Do** keep every surface flat and solid: quiet frame, white sheet, Answer Box. Text always sits on one of them.
- **Do** keep body text Ink on White Sheet and secondary text no lighter than Secondary Ink.
- **Do** draw every edge as a 1px Ink or Hairline rule, and keep corners square.
- **Do** number things: sheets (two digits), sections in the margin, figures per sheet.
- **Do** keep figures inline at a legible size and let wide ones scroll with a caption hint.
- **Do** set every count in mono or tabular figures.
- **Do** give every new state a distinct mark shape before giving it a colour.
- **Do** swap tokens in place for dark mode, using the neutral gray `*-dark` values.

### Don't:
- **Don't** put grids, patterns, gradients, tinted washes, or images behind text anywhere, including callouts and the frame.
- **Don't** tint the frame or sheet with a hue; the neutrals stay near-gray.
- **Don't** use Margin Red for anything other than the current position and the single next action.
- **Don't** use blur shadows, gradients, or translucent content surfaces.
- **Don't** round containers; circles belong to marks only.
- **Don't** set reading prose in Source Sans 3, or narrow prose into a column that no longer lines up with the figures.
- **Don't** put small uppercase labels above headings; the only small labels are the field names inside header strip cells.
- **Don't** turn the home into a card grid; sheets are listed as numbered rows.
