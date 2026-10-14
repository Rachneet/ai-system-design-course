# Visual style guide for lessons

Visuals carry as much of the teaching as the prose. Every lesson should have at least one sketch figure that
captures its central idea, and every important comparison, trade-off or number should be drawn, not only written.

## The three kinds of figure

| Block | Use it for | Rendering |
|---|---|---|
| ` ```viz ` | Explainers: comparisons (before and after, A against B), anatomy, numbers drawn as bars, grids of slots | HTML layout, then rough.js draws hand-drawn outlines and hatched fills |
| ` ```mermaid ` | Flows and sequences: pipelines, request paths, state machines, sequence diagrams | Mermaid's hand-drawn look |
| ` ```widget ` | Calculators where changing a number teaches something (`{"type": "kv"}`, `"cost"`, `"batch"`) | Live inputs and results |

## Writing a `viz` block

The first line may be `caption: ...` (inline markdown allowed). Everything after it is HTML using these primitives:

| Primitive | Markup | Notes |
|---|---|---|
| Columns | `<div class="vz-cols">...</div>`, `style="--k:3"` for 3 or 4 | Collapse to one column on phones |
| Panel | `<div class="vz-panel sk c"><h5>Title</h5>...</div>` | Rough outline in the panel's ink, no fill |
| Row | `<div class="vz-row">...</div>` | Wraps; holds chips, arrows, text |
| Chip | `<span class="ch sk m">text</span>`, add `wide` to stretch, `ghost` for dashed | Tinted fill in its ink |
| Arrow | `<span class="arr sk"></span>`, `arr long`, `arr d` (down) | Drawn by rough.js |
| Bars | `<div class="vz-bars"><span>label</span><span class="bar sk"><i class="sk g" style="--w:70%"></i></span><b>value</b></div>` | Repeat the three cells per row |
| Cell grid | `<div class="cells" style="--n:8"><i class="sk c">A</i><i class="sk x"></i>...</div>` | `fill` hatches a cell; `x` is cross-hatched waste |
| Big number | `<p class="big g">-93.3%</p>` | Ink classes below |
| Note | `<p>small explanatory text</p>` | Secondary ink |
| Source | `<div class="vz-src">Source: <a href="...">paper</a></div>` | Required when the figure shows a number |

Add `sk` to anything rough.js should draw. Without rough.js the same marks fall back to plain CSS borders.

## Inks: one meaning each

| Class | Meaning | Example |
|---|---|---|
| `c` | compute, prefill, the work, a request | GPU busy, prefill pool |
| `m` | memory, decode, storage, state | decode passes, KV pool |
| `g` | a win, met target, cache hit, allowed | goodput, "under 4% wasted" |
| `w` | a cost or a resource being spent | KV cache size, network, tokens |
| `b` | waste, failure, a miss, blocked | timed out, injection, idle slots |
| none | neutral | labels, inputs |

Never put hatching behind text. Use at most three inks in one figure. Red (`b`) means something went wrong.

## Rules

1. **One idea per figure**, stated in the caption as a conclusion ("A makes more tokens, but B serves more users
   well"), not a title ("Throughput comparison").
2. **Every number is sourced** under the figure, from a primary source (paper, official docs, engineering post).
   Peak results are labelled as peaks; vendor benchmarks are labelled as vendor benchmarks.
3. **Short labels.** Two to six words per chip. Explanations belong in the prose.
4. **Provider-neutral.** Show the pattern; name providers only as examples, and more than one when you do.
5. **Readable first.** High contrast, no textures behind text, nothing that only works on a wide screen.
6. No em or en dashes anywhere (the build fails on them).
