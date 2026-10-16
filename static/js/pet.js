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
//
// Leaving the page saves where it is and what it's doing, the chicken's brood
// with it, to this tab's sessionStorage, so a reload or a trip to another page
// and back carries on; closing the tab forgets it. Time away counts: its
// timers are kept as wall-clock times, so a nap that ran out meanwhile is over.

const SPEED = 34; // px per second
const RUN = 120; // px per second, running off after a startle
const DASH = [240, 360]; // px it runs off, between these: 2-3 s
const STROLL = 100; // px a walk goes at least: about 3 s
const SIT = [2500, 5000]; // ms it sits between walks
const WAG = 200; // ms per swish of the tail while it sits (the wag frame)
const STRIDE = 175; // ms per walking frame, in step with SPEED so feet don't slide
// Running, the legs keep a cadence of their own, quicker but still readable,
// and it hops once per stride in an arc up to HOP times its bounce (--lift)
// rather than bouncing on every frame, which read as vibrating.
const RUN_STRIDE = 90; // ms per running frame
const HOP = 2;
const WALK = ["walk1", "walk2", "walk3", "walk2"];
// Its body rises as its legs pass under it, in walk2, and drops as they
// spread: a bounce in step, a whole number of sprite pixels (--lift,
// assets/app.css), so it keeps to the pixel grid.
const LIFT = { walk2: "var(--lift)" };
const AWAKE = [60_000, 90_000]; // ms of wandering before it settles to sleep, picked each time it wakes
const NAP = [60_000, 120_000]; // ms asleep, between these
const REACTION = 1000; // ms a heart or "!" shows; its float is a little longer

let pet = null; // { el, x, timer, frame, wag, reaction, awakeSince, awakeFor, napUntil }

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
  clearInterval(pet.wag);
  cancelAnimationFrame(pet.frame);
  place(); // back on the ground
  show(frame);
  pet.timer = setTimeout(then, ms);
}

// Sitting, a dog wags its tail: sit and wag alternate. The duck's and pig's
// wag frame is their sit frame, so they stay still.
function sit() {
  rest("sit", between(...SIT), () => (Date.now() - pet.awakeSince > pet.awakeFor ? sleep() : walk()));
  if (!stillness.matches) pet.wag = setInterval(() => show(pet.el.dataset.frame === "sit" ? "wag" : "sit"), WAG);
}

function sleep(ms = between(...NAP)) {
  pet.napUntil = Date.now() + ms;
  rest("sleep", ms, wake);
}

function wake() {
  pet.awakeSince = Date.now();
  pet.awakeFor = between(...AWAKE);
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
  clearInterval(pet.wag);
  if (stillness.matches) return sleep();
  const running = speed > SPEED;
  const stride = running ? RUN_STRIDE : STRIDE;
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
    if (running) {
      // One arc per stride of four frames, in whole steps of --lift.
      const phase = ((now - began) % (stride * WALK.length)) / (stride * WALK.length);
      const height = Math.round(HOP * Math.sin(Math.PI * phase));
      place(height ? `calc(var(--lift) * ${height})` : undefined);
    } else {
      place(LIFT[frame]);
    }
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
  pet.awakeSince = Date.now();
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

// The chicken lays her first egg after 30 s to 1 min, and each one after that
// 2 to 10 min after the last, where she stands. A click
// hatches it: it cracks, and a chick comes out and follows her for the rest
// of the visit, in a line behind her. The chicks stop when she stops and
// sleep when she sleeps; a click on one gives a heart. Never more than BROOD
// eggs and chicks at once: with that many, she stops laying. They're saved
// with her, so they last as long as the tab does, and each viewer has their
// own. Eggs and chicks share a sheet, data-pet="brood" (assets/pets/brood.txt).
const FIRST_LAY = [30_000, 60_000]; // ms before her first egg
const LAY = [120_000, 600_000]; // ms between eggs after that
const BROOD = 3;
const SPACING = 6; // px between her and the first chick, and between chicks
const CHICK_SPEED = 60; // px per second: a little quicker than her, to keep up
const PEEP = 120; // ms per chick walking frame
const HATCH = 600; // ms an egg shows its crack before the chick comes out

let brood = []; // { el, x, kind: "egg" | "chick" }, in the order they came
let laying = null; // the next egg's timer
let layAt = null; // when it fires, in wall-clock ms
let wobbling = null; // the eggs' occasional wobble
let flock = null; // the chicks' animation frame

const isHen = () => pet && pet.el.dataset.pet === "chicken";
const chicks = () => brood.filter((one) => one.kind === "chick");

function hatchling(kind, x) {
  const el = document.createElement("button");
  el.type = "button";
  el.className = "pet pointer-events-auto absolute bottom-2 left-4 cursor-pointer rounded-md";
  el.dataset.pet = "brood";
  el.dataset.frame = kind;
  el.setAttribute("aria-label", kind === "egg" ? "Hatch the egg" : "Pet the chick");
  pet.el.parentElement.append(el);
  const one = { el, x: Math.max(0, x - el.offsetWidth / 2), kind };
  el.style.translate = `${one.x}px 0`;
  brood.push(one);
  return one;
}

function layLater(ms = between(...(brood.length ? LAY : FIRST_LAY))) {
  clearTimeout(laying);
  if (isHen() && brood.length < BROOD) {
    layAt = Date.now() + ms;
    laying = setTimeout(lay, ms);
  }
}

// Under her middle; then she settles a moment. Not while she sleeps.
function lay() {
  if (!isHen()) return;
  if (pet.el.dataset.frame !== "sleep") {
    hatchling("egg", pet.x + pet.el.offsetWidth / 2);
    sit();
  }
  layLater();
}

function hatch(egg) {
  if (egg.el.dataset.frame === "crack") return;
  egg.el.dataset.frame = "crack";
  setTimeout(() => {
    egg.kind = "chick";
    egg.el.dataset.frame = "chick";
    egg.el.setAttribute("aria-label", "Pet the chick");
    follow();
  }, HATCH);
}

function cheep(chick) {
  delete chick.el.dataset.reaction;
  void chick.el.offsetWidth; // restart the float
  chick.el.dataset.reaction = "heart";
  setTimeout(() => delete chick.el.dataset.reaction, REACTION);
}

// Now and then an egg rocks, a hint that it can be clicked.
function wobble() {
  for (const egg of brood) {
    if (egg.kind === "egg" && egg.el.dataset.frame === "egg" && Math.random() < 0.3) {
      egg.el.dataset.frame = "wobble";
      setTimeout(() => egg.el.dataset.frame === "wobble" && (egg.el.dataset.frame = "egg"), 250);
    }
  }
}

// The chicks walk to their places in a line behind her, in hatching order.
function follow() {
  if (flock) return;
  let last = performance.now();
  const step = (now) => {
    const elapsed = Math.min(now - last, 100);
    last = now;
    const asleep = pet.el.dataset.frame === "sleep" || stillness.matches;
    const behind = pet.el.dataset.facing === "left" ? 1 : -1;
    let reach = pet.el.offsetWidth / 2 + SPACING;
    for (const chick of chicks()) {
      const width = chick.el.offsetWidth;
      const edge = chick.el.parentElement.clientWidth - width - 32;
      const centre = pet.x + pet.el.offsetWidth / 2 + behind * (reach + width / 2);
      reach += width + SPACING;
      const goal = Math.min(Math.max(centre - width / 2, 0), edge);
      const gap = goal - chick.x;
      let lift = "0px";
      if (asleep) {
        chick.el.dataset.frame = "chick-sleep";
      } else if (Math.abs(gap) > 1) {
        const speed = Math.abs(gap) > 100 ? RUN : CHICK_SPEED; // dash to catch up
        chick.x += Math.sign(gap) * Math.min((speed * elapsed) / 1000, Math.abs(gap));
        chick.el.dataset.facing = gap < 0 ? "left" : "right";
        chick.el.dataset.frame = Math.floor(now / PEEP) % 2 ? "chick-walk1" : "chick-walk2";
        // A hop in its step, but not running to catch up, when it would vibrate.
        lift = speed === CHICK_SPEED && chick.el.dataset.frame === "chick-walk2" ? "var(--lift)" : "0px";
      } else {
        chick.el.dataset.facing = pet.el.dataset.facing || "right";
        chick.el.dataset.frame = "chick";
      }
      chick.el.style.translate = `${chick.x}px ${lift}`;
    }
    flock = requestAnimationFrame(step);
  };
  flock = requestAnimationFrame(step);
}

function stop() {
  if (!pet) return;
  clearTimeout(pet.timer);
  clearTimeout(pet.reaction);
  clearInterval(pet.wag);
  cancelAnimationFrame(pet.frame);
  clearTimeout(laying);
  layAt = null;
  clearInterval(wobbling);
  cancelAnimationFrame(flock);
  flock = null;
  for (const one of brood) one.el.remove();
  brood = [];
  pet = null;
}

// What this tab saved on this board when it last left, taken once: a pet
// chosen from the menu later starts afresh.
const KEY = `pet:${location.pathname}`;
let saved = JSON.parse(sessionStorage.getItem(KEY));
sessionStorage.removeItem(KEY);

function save() {
  if (!pet) return;
  sessionStorage.setItem(KEY, JSON.stringify({
    kind: pet.el.dataset.pet,
    x: pet.x,
    facing: pet.el.dataset.facing,
    asleep: pet.el.dataset.frame === "sleep",
    napUntil: pet.napUntil,
    awakeSince: pet.awakeSince,
    awakeFor: pet.awakeFor,
    layAt,
    // Centres, as hatchling() takes them.
    brood: brood.map((one) => ({ kind: one.kind, x: one.x + one.el.offsetWidth / 2 })),
  }));
}

// For the page, and again whenever choosing a pet swaps #pet in.
function start(root) {
  const el = root.querySelector("[data-pet]");
  if (!el && root.id !== "pet") return;
  stop();
  if (!el) return;
  const was = saved?.kind === el.dataset.pet ? saved : null;
  saved = null;
  pet = { el, x: was?.x ?? 0, timer: null, frame: null, wag: null, reaction: null, awakeSince: was?.awakeSince ?? Date.now(), awakeFor: was?.awakeFor ?? between(...AWAKE), napUntil: null };
  if (was?.facing) el.dataset.facing = was.facing;
  if (stillness.matches) sleep();
  else if (was?.asleep) was.napUntil > Date.now() ? sleep(was.napUntil - Date.now()) : wake();
  else sit();
  if (isHen()) {
    for (const one of was?.brood ?? []) hatchling(one.kind, one.x);
    if (chicks().length) follow();
    layLater(was?.layAt == null ? undefined : Math.max(0, was.layAt - Date.now()));
    if (!stillness.matches) wobbling = setInterval(wobble, 1500);
  }
}

htmx.onLoad(start);
window.addEventListener("pagehide", save);
document.addEventListener("click", (event) => {
  if (!pet) return;
  const clicked = event.target.closest("[data-pet]");
  if (clicked === pet.el) return petted();
  const one = brood.find((b) => b.el === clicked);
  if (one) one.kind === "egg" ? hatch(one) : cheep(one);
});
window.addEventListener("resize", () => pet && place());
stillness.addEventListener("change", () => pet && (stillness.matches ? sleep() : wake()));
