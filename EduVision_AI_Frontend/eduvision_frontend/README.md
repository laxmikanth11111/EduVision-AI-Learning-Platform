# EduVision AI — Frontend Design Package

> **DEPRECATED — DO NOT MODIFY.** This directory is a static design prototype
> preserved for historical reference only. It is **not** served by the
> application and is **not** the canonical frontend. All active frontend work
> lives in `backend/frontend/`. Do not add features, fix bugs, or make any
> changes here. This directory will be removed once the archived design is no
> longer referenced.

A complete, interactive HTML/CSS/Bootstrap frontend concept for EduVision AI —
a tool that turns any topic or uploaded document into a short visual
explanation (animation, image, video, or simulation), with no accounts
required to try it and no role-based access restrictions.

## How to view it

No build step needed. Just open `index.html` in any browser — every page
links to the next, so you can click through the whole flow:

1. **index.html** — landing page, product pitch, animated hero
2. **signup.html** / **signin.html** — account creation and login
3. **upload.html** — start a deck: upload a document or type topics
4. **processing.html** — AI extraction progress, then topic review with
   per-topic visual-type selection
5. **player.html** — the core experience: description → visual → Next,
   repeated per topic, with Play/Pause/Restart on the animation
6. **components.html** — the shared design system (buttons, forms, cards,
   badges, progress, toggle, tabs, avatar) used to build every screen

## Structure

```
index.html
signin.html
signup.html
upload.html
processing.html
player.html
components.html
assets/
  style.css   — shared design tokens, components, animations
  app.js      — shared interactions (scroll reveal, tabs, toggles)
```

## Design language

- Deep ink-navy background with amber / teal / coral accent colors
- Space Grotesk for headings, Manrope for body text
- Sharp-edged "framed" cards with corner ticks, no heavy shadows or gradients
- Motion used deliberately: staggered entrance animations, scroll-triggered
  reveals, a synced stage indicator on the water cycle animation, and
  hover micro-interactions — all respecting `prefers-reduced-motion`

## Notes for building the real product

- This is a static design concept — forms don't submit anywhere, and the
  "AI processing" step is a timed simulation, not real extraction.
- The player screen demonstrates the exact interleaved topic → visual → next
  topic pattern from the project spec, using the water cycle and
  photosynthesis as example topics.
- Swap in real AI-generated content per topic, and connect the upload /
  processing screens to your actual backend pipeline.
