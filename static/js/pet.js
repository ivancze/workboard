// The board's pet (components/pet.html) wanders along the bottom of the
// window. It walks to a random spot, sits a while, and walks again. After a
// quiet spell it falls asleep for a while, then gets up by itself. Frames are
// picked with data-frame (assets/app.css).
//
// A click (or Enter or Space, since it's a button) wakes it with a start if
// it's asleep. Awake, it either loves it (a heart) or is startled (a hop and
// a "!") and runs off. Either way it's awake for a while longer.
//
// Walking runs on requestAnimationFrame, which stops while the tab is hidden.
// Sitting and sleeping are timers, so a pet at rest costs nothing per frame.
// With reduced motion it never walks: it sleeps where it is.

const SPEED = 40; // px per second
const RUN = 120; // px per second, running off after a startle
const DASH = [360, 540]; // px it runs off, between these: 3-4.5 s
const STROLL = 100; // px a walk goes at least: 2.5 s
const SIT = [1000, 3000]; // ms it sits between walks
const STRIDE = 150; // ms per walking frame
const WALK = ["walk1", "walk2", "walk3", "walk2"];
// Its body rises one sprite pixel (--pixel, assets/app.css) as its legs pass
// under it, in walk2, and drops as they spread: a bounce in step, kept to the
// pixel grid.
const LIFT = { walk2: "calc(var(--pixel) * -1)" };
const AWAKE_FOR = 180_000; // ms of wandering before it settles to sleep
const NAP = [60_000, 120_000]; // ms asleep, between these
const REACTION = 1000; // ms a heart or "!" shows; its float is a little longer

let pet = null; // { el, x, timer, frame, reaction, awakeSince }

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
  rest("sit", between(...SIT), () => (performance.now() - pet.awakeSince > AWAKE_FOR ? sleep() : walk()));
}

function sleep() {
  rest("sleep", between(...NAP), wake);
}

function wake() {
  pet.awakeSince = performance.now();
  walk();
}

// Somewhere at least a stroll away, on whichever side has room for it.
function wander() {
  const width = room();
  const sides = [];
  if (pet.x - STROLL > 0) sides.push(between(0, pet.x - STROLL));
  if (pet.x + STROLL < width) sides.push(between(pet.x + STROLL, width));
  return sides.length ? sides[Math.floor(Math.random() * sides.length)] : between(0, width);
}

function walk(target = wander(), speed = SPEED) {
  if (stillness.matches) return sleep();
  const stride = (STRIDE * SPEED) / speed; // quicker steps when running
  pet.el.dataset.facing = target < pet.x ? "left" : "right";
  let last = performance.now();
  const began = last;
  const step = (now) => {
    // A long gap means the tab was hidden; carry on from where it was.
    const elapsed = Math.min(now - last, 100);
    last = now;
    const distance = (speed * elapsed) / 1000;
    const goal = Math.min(target, room()); // the window may have narrowed
    pet.x += Math.sign(goal - pet.x) * Math.min(distance, Math.abs(goal - pet.x));
    const frame = WALK[Math.floor((now - began) / stride) % WALK.length];
    place(LIFT[frame]);
    show(frame);
    if (Math.abs(goal - pet.x) < 0.5) return sit();
    pet.frame = requestAnimationFrame(step);
  };
  pet.frame = requestAnimationFrame(step);
}

// Shows a heart or a "!" above its head, starting it over if one is already
// showing, so every click gets its own.
function react(reaction) {
  clearTimeout(pet.reaction);
  delete pet.el.dataset.reaction;
  void pet.el.offsetWidth; // let the browser see it go, so the animation restarts
  pet.el.dataset.reaction = reaction;
  const el = pet.el;
  pet.reaction = setTimeout(() => delete el.dataset.reaction, REACTION);
}

function petted() {
  const asleep = pet.el.dataset.frame === "sleep";
  pet.awakeSince = performance.now();
  if (asleep) {
    react("startled");
    rest("startled", 600, sit);
  } else if (Math.random() < 0.5) {
    react("heart");
    rest("happy", 1200, sit);
  } else {
    react("startled");
    rest("startled", 400, runOff);
  }
}

// A short dash, about a second, towards whichever side has more room.
function runOff() {
  const dash = between(...DASH);
  walk(pet.x > room() / 2 ? Math.max(0, pet.x - dash) : Math.min(room(), pet.x + dash), RUN);
}

function stop() {
  if (!pet) return;
  clearTimeout(pet.timer);
  clearTimeout(pet.reaction);
  cancelAnimationFrame(pet.frame);
  pet = null;
}

// For the page, and again whenever choosing a pet swaps #pet in.
function start(root) {
  const el = root.querySelector("[data-pet]");
  if (!el && root.id !== "pet") return;
  stop();
  if (!el) return;
  pet = { el, x: 0, timer: null, frame: null, reaction: null, awakeSince: performance.now() };
  stillness.matches ? sleep() : sit();
}

htmx.onLoad(start);
document.addEventListener("click", (event) => {
  if (pet && event.target.closest("[data-pet]") === pet.el) petted();
});
window.addEventListener("resize", () => pet && place());
stillness.addEventListener("change", () => pet && (stillness.matches ? sleep() : wake()));
