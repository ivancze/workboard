# Frontend conventions

Tailwind v4 through its standalone CLI, so there is no Node toolchain. The
stylesheet source is `assets/app.css`; the output, `static/css/app.css`, is
generated and never committed.

## Running it

`docker compose up` starts a `css` service that rebuilds the stylesheet
whenever a template changes. Nothing else needs to run.

It polls, like Django's autoreloader. A watcher that waits for file events never
hears about edits made on the host, because those events do not cross Colima's
virtiofs mount: it builds once and then stays silent, with no error. This was
checked both ways during ticket 05a. A host edit reached the served stylesheet
in under a second with polling, and never arrived without it.

`bin/tailwind` pins the CLI version and the checksum of each platform's binary,
and downloads it into `.bin/` on first use. To move to a new version, change
`VERSION` and the four checksums together, taking them from the release's
`sha256sums.txt`.

The Docker image runs `bin/tailwind build --minify` before `collectstatic`, so a
failed Tailwind build fails the image.

## Rules

**Colours are semantic tokens.** `@theme` in `assets/app.css` defines the only
colours that exist (`bg-surface`, `text-text-muted`, `border-control` and so
on). Tailwind's palette is switched off, so `bg-blue-500` generates nothing.
Each token holds its light and dark value in `light-dark()`, so a component
built from tokens supports both themes with no `dark:` variants. Keep `dark:`
for genuine exceptions.

`light-dark()` was chosen over redefining the variables under
`[data-theme=dark]`, which the ticket first proposed, because it lets System
follow an OS change live with no JavaScript. The cost is browser support: Safari
17.5, Chrome 123 and Firefox 120 are the minimum, and older browsers treat every
colour as invalid. That is acceptable for a small team on current browsers.

**No arbitrary values.** Never write `p-[13px]` or `bg-[#3b82f6]`. If a value is
missing from the scale, add it to `@theme` as a token. A test fails on any
`[` in a template class.

One copied colour is the tab icon, `static/favicon.svg`, which holds the
light theme's `--color-text` as a hex value because a favicon cannot read the
stylesheet. It uses the light value in both themes: on a dark tab bar the
tile's edge fades, but its white bars still read. Change it by hand when that
token changes.

Another is Google's "G" on the sign-in button
(`components/google_mark.html`), in Google's own four colours. A brand mark
isn't recoloured, and Google allows it only on a white or neutral
background, so that button uses the bordered `secondary` variant rather than
the accent.

The third is the board pets' sprites (`assets/pets/`), whose palettes are hex
inside the pixel grids, because an image can't read the stylesheet. They use
the same colours in both themes, and each animal is light enough to read on
the dark canvas, with a dark outline for the light one.

**Contrast is tested.** A test reads each token's light and dark value from
`assets/app.css` and checks the WCAG AA pairs: 4.5:1 for text, and 3:1 for
control edges and the focus ring. A new token that carries text or marks a
control belongs in its pair list.

**Components are template partials**, in `templates/components/`, each carrying
its own utility classes. Reuse them with `{% include %}`, not with `@apply`. A
partial is also the fragment that HTMX will swap.

**Form controls come from widget templates.** `templates/django/forms/widgets/`
overrides Django's `input.html` and `textarea.html` (the setting is
`FORM_RENDERER = TemplatesSetting`), so `{{ field }}` renders a styled control.
`components/fields.html` lays out a whole form.

**Some styles live in the base layer**, because markup there cannot take
classes: the keyboard focus ring for every interactive element, links in
library-rendered text, the reduced-motion override, the colours of rendered
markdown (`prose prose-tokens`), and the rule that suspends colour transitions
for the instant of a theme switch, so nothing fades across while the rest of
the page has already changed.

**Type** uses three families, all loaded from Google Fonts in `base.html` and
named in `assets/app.css`:

- Poppins (`font-display font-extrabold tracking-tight`) for the page's h1.
- Bebas Neue (`font-condensed tracking-wide`) for the wordmark, section titles
  and Stage names. It has one weight and only capitals, so never give it a
  weight class, and don't use it for text people type, which it would shout.
- Plus Jakarta Sans (`--font-sans`) for everything else, with `font-semibold`
  for labels, buttons and Card titles.

To try another font, change the family in both places.

## Theme

The toggle cycles System → Light → Dark and stores the choice in
`localStorage`. A stored choice becomes `data-theme` on `<html>`. System is
stored as no choice at all, and the stylesheet then follows the OS, live, with
no JavaScript. An inline script in `base.html` applies the choice before the
stylesheet loads, so the first paint is already correct.

While judging the themes, turn off dark-mode browser extensions for localhost.
Dark Reader, for one, forces `color-scheme: dark` and repaints the page, which
makes the app's own colours impossible to see.

## Scripts

Pages work without JavaScript; scripts only make them quicker to use. Every
page loads htmx from `base.html`, which sends Django's CSRF token as a header
through `hx-headers` on `<body>`. A page adds its own scripts in
`{% block scripts %}`.

**Vendored, not fetched.** Third-party scripts live in `static/vendor/`, served
by the app rather than from a CDN at runtime:

| File | Version | SHA-256 |
|---|---|---|
| `htmx.min.js` | htmx 2.0.11 | `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717` |
| `Sortable.min.js` | SortableJS 1.15.7 | `bf4241bc73fef7f11c59a283a69fe8051cdd31c6d8ff5a2b9ba219e7831fcf76` |

A test checks both hashes. To upgrade, download the new release from
jsDelivr, check that unpkg serves identical bytes, and update this table and
`VENDORED` in `config/tests/test_design_system.py` together.

**Drag and drop** (`static/js/board.js`) posts each drop to the same move
endpoint as the Move items in each Card's ⋯ menu
(`components/card_menu.html`), with the Card's new Stage and the Card it
landed beside: `before`, the tile just below it, or `after`, the one just
above when it is last. Never an index, which a filter hiding Cards, or a stale
page, would make wrong; the server resolves the neighbour under the Stage
locks. The server answers with `components/board.html`, the board's totals and Stages
fresh from the database, and htmx swaps it in. The page therefore always shows
where the server actually put the Card. A failed save fetches the board again
for the same reason. Every Stage keeps its `<ol data-card-list>` even when it
is empty, so a Card can be dropped into it. While dragging, the spot where the
Card will land is an empty dashed outline: Sortable's placeholder, given the
`card-placeholder` class, styled in `assets/app.css`.

**Refresh on return** (`board.js`, ticket 18, ADR 0001). When the tab becomes
visible or the window regains focus, `board.js` fetches `#board`'s
`data-board-url`, which carries the filter, and swaps in the `#board` from the
page that comes back, as after a failed drop. There is no timer and no open
connection, and a hidden tab requests nothing. A refresh is not sent while a
drag (`Sortable.dragged`), an open ⋯ menu or dialog, or another htmx request
is in progress. All htmx requests here queue on `<body>`, so a refresh never
overtakes a move. An answer arriving after a drag has started, or with a menu
or dialog open, is dropped rather than swapped, and the next return catches up.
An error, or a page without a board (a redirect to sign in), leaves the board as
it is and shows `#refresh-failed`, which sits outside `#board` so no swap
removes it. Any board swap keeps the Stage row's sideways scroll
(`data-stage-row`).

**The ⋯ menus** on each Card (`components/card_menu.html`), each Stage
(`components/stage_menu.html`) and the board (`components/board_menu.html`),
and a Card's Priority dropdown (`components/priority_menu.html`), are
`<details data-menu>` dropdowns, so they work without JavaScript. `board.js` closes one on a click elsewhere or Escape,
and pins an open menu to the window (`position: fixed`), below its ⋯ button
or above it when there is no room below. A panel lines up with its button's
right edge, or with its left edge with `data-menu-start`, as for the Priority
pill at a Card's left. The Stage row scrolls sideways, and
that also clips anything overflowing its bottom, so a menu left inside it
would be cut off on the lowest Card. Scrolling closes an open menu rather than
leaving it behind, and so does choosing an item that opens a dialog.

**Editing in place: the board's name and description.** For the Owner, the
pencil beside the name (`components/board_heading.html`) and the description
itself (`components/board_description.html`) are links to the rename and
description pages, which is what they stay without JavaScript. Both are
`data-in-place` elements. With htmx, each swaps for a form with the same id
(`board_rename_form.html`, `board_description_form.html`).
- `board.js` focuses and selects the field. It keeps a copy of what the form
  replaced, so Escape, Cancel or a click elsewhere put it back without a
  round trip. Opening one closes the other.
- Saving returns the element, and focus goes back to its link. The name
  also returns a `<title>`, which htmx applies to the tab.
- A refused value comes back as a 400 carrying its error. `board.js` lets
  htmx swap it in, and clears its error status, which would otherwise make
  `restoreBoard` reload the board.
- A board with no description shows a playful line, picked at random by the
  view on each load (`PLAYFUL_DESCRIPTIONS`). The description's form starts
  empty, not from that line.

**Subtasks** (`components/subtasks.html`, `static/js/subtasks.js`). On a
Card's page every Subtask action is a small form: tick, rename, ↑↓, delete and
add. Without JavaScript each posts and comes back to the page. With htmx each
answers with the whole `#subtasks` section, swapped in place, and a refused
value comes back as a 400 that `subtasks.js` lets htmx swap in, error and all.
- A tick box is a `<button role="checkbox">`, so it submits without
  JavaScript. It sends the state wanted, never "toggle", so two people ticking
  from the same stale page both mean done.
- A Subtask's text is a borderless field in a form of its own: Enter saves it,
  and `subtasks.js` puts it back on Escape or when it loses focus unsaved.
- Each box, arrow and field carries an id, so htmx returns focus to it after
  the swap. Ticking down a list by keyboard keeps its place, and the add field
  stays focused for the next one.
- Progress is a native `<progress>`, on the page and on the Card's tile,
  styled as `.subtask-progress` in `assets/app.css`. Its width needs no
  arbitrary value, and it carries its own semantics.

New card and Edit show the Subtasks as rows (`components/subtask_rows.html`),
an inline formset. × is the formset's delete checkbox, hidden behind the
symbol, so removing works without JavaScript; the row dims until saved.
`subtasks.js` shows + Add, which focuses the blank last row or copies the
formset's empty form from a `<template>`. Without JavaScript the one blank row
stands in for it, a Subtask per save.

**The board pet** (`components/pet.html`) is pixel art. Each animal is a
text file of square grids, one frame per grid, in `assets/pets/`: 16×16 for
the duck, 18×18 for the chicken, 28×28 for the pug, 36×36 for the pig, 74×74
for Chico and 84×84 for Bruno. All six were read from reference images by
sampling their pixel grids:
- the pug, the duck (a mallard) and the chicken, from free sources
- the pig, licensed from Dreamstime
- Chico (a tan mixed breed) and Bruno (a black Labrador), generated by the
  user

`bin/pets` builds them into the sprite sheets in `static/pets/`, frames side
by side in its `FRAMES` order. The sheets are committed, and a test rebuilds
them and fails if they differ, so after editing a grid, run `bin/pets` and
commit both. `assets/app.css` draws them with `image-rendering: pixelated`.
`--grid` is a frame's size in sprite pixels and `--pixel` one sprite pixel on
screen:
- 3 px for the duck (48 px) and the chicken (54 px)
- 2 px for the pug (56 px) and the pig (72 px)
- 1 px for Chico (74 px) and Bruno (84 px), their full detail

The chicken's eggs and chicks have a sheet of their own, `brood.txt`, 14×14 at
2 px (28 px). It isn't a pet, so it lists its own frames on a `frames:` line
in place of `FRAMES`: egg, wobble, crack, chick, chick-walk1, chick-walk2 and
chick-sleep. Their `--frame` indexes come from that line, and the frame test
checks both lists.

The strip they stand on is `h-24` (96 px), the height Bruno needs.

The pet is sized from them, and the bounce and the hop move in `--pixel`, so
they stay on that animal's grid.
`data-frame` picks the frame.
- The pet stands on a strip fixed to the bottom of the window. The strip lets
  clicks through and only the pet takes them, so it never blocks a Card, a
  menu or a drag. In the page's flow, `#pet` holds the strip's height free,
  so the lowest Card can scroll clear of it.
- `#pet` sits outside `#board`, because a drag or a refresh swaps `#board`
  and would reset it. So another Member's change shows on the next page load,
  not on refresh-on-return.
- It's chosen from the board's ⋯ menu. With htmx, the answer is `#pet`, plus
  the menu out of band (`oob`), closed, with the new choice ticked.
- `static/js/pet.js` moves it, and the board page loads it even with no pet,
  since one chosen from the menu arrives without a page load. It walks at
  34 px/s (`SPEED`), at least 100 px (`STROLL`), to a random spot, sits for
  2.5-5 s (`SIT`), walks again, and after 60-90 s awake (`AWAKE`, picked each
  time it wakes) sleeps for a minute or two. A startle sends it dashing
  240-360 px (`DASH`), about 2-3 s.
- Sitting, the dogs wag their tails: `sit` and `wag` alternate every 200 ms
  (`WAG`). The duck's and pig's `wag` is their `sit` (`== wag = sit` in their
  grids), so they stay still. Reduced motion skips the wag.
- Walking runs on `requestAnimationFrame`; sitting and sleeping are timers,
  so a pet at rest costs nothing per frame. A pet swapped in replaces the old
  one's loop, and takes any eggs and chicks with it.
- The chicken lays her first egg after 30 s to 1 min (`FIRST_LAY`), and each
  one after that 2 to 10 min after the last (`LAY`), where she stands, but
  not while she sleeps. An egg wobbles now and then until it's clicked. Then
  it cracks, and a chick hatches and follows her in a line, stopping when she
  stops and sleeping when she sleeps. A click on a chick gives a heart. There
  are never more than three eggs and chicks (`BROOD`); with three, she stops
  laying. They live only in the page, so each visit starts afresh and each
  viewer has their own.
- The sheets face right. Walking left sets `data-facing="left"`, which
  mirrors it with `scale`, leaving `translate` free for its position.
- Walking, it bounces in step: its body rises as its legs pass under it
  (walk2) and drops as they spread. The rise is `--lift`, a whole number of
  sprite pixels so it stays on the grid: one for most pets (2-3 px), and two
  for Chico and Bruno (2 px), whose pixels are small. Chicks hop by one of
  theirs (2 px) on every other step. A dash runs its legs at 90 ms a frame
  (`RUN_STRIDE`) and, instead of bouncing every step, hops once per stride in
  an arc up to twice its bounce (`HOP`), in whole steps of `--lift`. A chick
  catching up doesn't hop.
- Asleep, a "z" drifts up from its head: CSS on the sleep frame, in a token
  colour, mirrored back when it faces left so the letter reads.
- A click, or Enter or Space since it's a button, gets a reaction. Asleep,
  it wakes with a start. Awake, it's either happy, with a heart, or startled,
  with a hop and a "!", and dashes a short way towards the roomier side.
  Either way it stays awake for longer. The heart and the "!" are pixel
  shapes used as CSS masks, filled from tokens (`danger`, `text`), so they
  keep to the grid and suit both themes.
- With reduced motion it never walks. It sleeps where it is, and the global
  override leaves the "z", the heart and the "!" standing still. A click
  still shows a reaction.

**Confirmation dialogs** (`components/confirm_dialog.html`) are native
`<dialog>` elements, opened by a button with `commandfor="<dialog id>"` and
`command="show-modal"`, so they need no JavaScript: Cancel and Escape close
them. Invoker commands need Chrome 135, Firefox 144 or Safari 26.2; an older
browser ignores the button. Keep a dialog outside any `<details>` menu, which
hides its contents when closed, and outside any other form. The confirm
button takes a `variant`: `danger` (with the `danger`, `on-danger` and
`danger-hover` tokens) for what can't be undone.

**Landing and confetti.** A Card arriving from another Stage carries
`data-landed`, and the `animate-land` animation (defined in `@theme`) plays
through the `data-landed:` variant. In the board's last Stage it also carries
`data-celebrate`, and `board.js` throws confetti: plain `.confetti` elements
styled in `assets/app.css`, coloured with the theme tokens, and removed on a
timer. A timer is used rather than `animationend`, which a hidden tab suspends.
After a drag, `board.js` sets both marks itself, on the drop, rather than a
round trip later when the server's board arrives. The board fragment carries
no mark, and the pulse is resumed on the swapped-in tile at the point it had
reached, through a negative `animation-delay`. After a Move item, the view
sets the mark in the session for the page it redirects to. Either way it plays
once. Reduced motion skips the confetti, and the global override stills the
landing animation.

