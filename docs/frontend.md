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
(`components/card_menu.html`), with the Card's new Stage and position. The
server answers with `components/board.html`, the board's totals and Stages
fresh from the database, and htmx swaps it in. The page therefore always shows
where the server actually put the Card. A failed save fetches the board again
for the same reason. Every Stage keeps its `<ol data-card-list>` even when it
is empty, so a Card can be dropped into it. While dragging, the spot where the
Card will land is an empty dashed outline: Sortable's placeholder, given the
`card-placeholder` class, styled in `assets/app.css`.

**The ⋯ menus** on each Card (`components/card_menu.html`) and each Stage
(`components/stage_menu.html`) are `<details data-menu>` dropdowns, so they
work without JavaScript. `board.js` closes one on a click elsewhere or Escape,
and pins an open menu to the window (`position: fixed`), below its ⋯ button
or above it when there is no room below. The Stage row scrolls sideways, and
that also clips anything overflowing its bottom, so a menu left inside it
would be cut off on the lowest Card. Scrolling closes an open menu rather than
leaving it behind, and so does choosing an item that opens a dialog.

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
The views set the mark, in the board fragment after a drag, or in the session
for the page a Move item redirects to, so it plays once. Reduced motion skips
the confetti, and the global override stills the landing animation.

