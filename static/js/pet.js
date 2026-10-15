// The board's pet (components/pet.html) wanders along the bottom of the
// window. It walks to a random spot, sits a while, and walks again. After a
// quiet spell it falls asleep for a while, then gets up by itself. Frames are
// picked with data-frame (assets/app.css).
//
// Walking runs on requestAnimationFrame, which stops while the tab is hidden.
// Sitting and sleeping are timers, so a pet at rest costs nothing per frame.
// With reduced motion it never walks: it sleeps where it is.

const SPEED = 40; // px per second
const STRIDE = 150; // ms per walking frame
const WALK = ["walk1", "walk2", "walk3", "walk2"];
// Its body rises one sprite pixel (3 px at 3x) as its legs pass under it, in
// walk2, and drops as they spread: a bounce in step, kept to the pixel grid.
const LIFT = { walk2: "-0.1875rem" };
const AWAKE_FOR = 45_000; // ms of wandering before it settles to sleep
const NAP = [60_000, 120_000]; // ms asleep, between these

let pet = null; // { el, x, timer, frame, awakeSince }

const between = (low, high) => low + Math.random() * (high - low);
const stillness = matchMedia("(prefers-reduced-motion: reduce)");

// How far right it may go: the strip's width, less the pet and the gutter
// its left-4 keeps on each side. Read every time, so a resize is followed.
function room() {
  return Math.max(0, pet.el.parentElement.clientWidth - pet.el.offsetWidth - 32);
}

function place(lift = "0px") {
  pet.x = Math.min(pet.x, room());
  pet.el.style.translate = `${pet.x}px ${lift}`;
}

function show(frame) {
  pet.el.dataset.frame = frame;
}

function rest(frame, ms, then) {
  clearTimeout(pet.timer);
  cancelAnimationFrame(pet.frame);
  place(); // back on the ground
  show(frame);
  pet.timer = setTimeout(then, ms);
}

function sit() {
  rest("sit", between(2000, 6000), () => (performance.now() - pet.awakeSince > AWAKE_FOR ? sleep() : walk()));
}

function sleep() {
  rest("sleep", between(...NAP), wake);
}

function wake() {
  pet.awakeSince = performance.now();
  walk();
}

function walk() {
  if (stillness.matches) return sleep();
  const target = between(0, room());
  pet.el.dataset.facing = target < pet.x ? "left" : "right";
  let last = performance.now();
  const began = last;
  const step = (now) => {
    // A long gap means the tab was hidden; carry on from where it was.
    const elapsed = Math.min(now - last, 100);
    last = now;
    const distance = (SPEED * elapsed) / 1000;
    const goal = Math.min(target, room()); // the window may have narrowed
    pet.x += Math.sign(goal - pet.x) * Math.min(distance, Math.abs(goal - pet.x));
    const frame = WALK[Math.floor((now - began) / STRIDE) % WALK.length];
    place(LIFT[frame]);
    show(frame);
    if (Math.abs(goal - pet.x) < 0.5) return sit();
    pet.frame = requestAnimationFrame(step);
  };
  pet.frame = requestAnimationFrame(step);
}

function stop() {
  if (!pet) return;
  clearTimeout(pet.timer);
  cancelAnimationFrame(pet.frame);
  pet = null;
}

// For the page, and again whenever choosing a pet swaps #pet in.
function start(root) {
  const el = root.querySelector("[data-pet]");
  if (!el && root.id !== "pet") return;
  stop();
  if (!el) return;
  pet = { el, x: 0, timer: null, frame: null, awakeSince: performance.now() };
  stillness.matches ? sleep() : sit();
}

htmx.onLoad(start);
window.addEventListener("resize", () => pet && place());
stillness.addEventListener("change", () => pet && (stillness.matches ? sleep() : wake()));
