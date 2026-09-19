import { useEffect } from "react";

// Standard Gamepad API mapping ("standard" gamepad_mapping) — Xbox-style
// layout, which is what Steam Input/SDL present Deck controls as too.
const BTN_A = 0;
const BTN_B = 1;
const BTN_X = 2;
const BTN_START = 9;
const BTN_DPAD_UP = 12;
const BTN_DPAD_DOWN = 13;
const BTN_DPAD_LEFT = 14;
const BTN_DPAD_RIGHT = 15;

const STICK_DEADZONE = 0.5;
const REPEAT_INITIAL_DELAY_MS = 350;
const REPEAT_INTERVAL_MS = 130;

type Direction = "up" | "down" | "left" | "right";

const FOCUSABLE_SELECTOR =
  'button:not(:disabled), [tabindex="0"], input:not(:disabled), select:not(:disabled), a[href]';

function isVisible(el: Element): boolean {
  return (el as HTMLElement).offsetParent !== null;
}

// Background screens stay mounted behind an open modal (e.g. GameGrid's
// {gameModal && <GameModal/>}), so navigation must be scoped to the topmost
// modal when one is open — otherwise D-pad could focus a hidden card behind it.
function focusScope(): ParentNode {
  const overlays = document.querySelectorAll(".modal-overlay");
  return overlays.length ? overlays[overlays.length - 1] : document;
}

function getFocusables(): HTMLElement[] {
  return Array.from(focusScope().querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(isVisible);
}

// Nearest-candidate-in-direction: filter to elements strictly past the
// current one along the primary axis, then score by primary distance +
// perpendicular offset (weighted so a same-row/column match wins over a
// closer-but-diagonal one).
function findNextFocusable(current: HTMLElement, dir: Direction): HTMLElement | null {
  const candidates = getFocusables().filter((el) => el !== current);
  const from = current.getBoundingClientRect();
  const fromX = from.left + from.width / 2;
  const fromY = from.top + from.height / 2;

  let best: HTMLElement | null = null;
  let bestScore = Infinity;

  for (const el of candidates) {
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const dx = cx - fromX;
    const dy = cy - fromY;

    let primary: number;
    let perpendicular: number;
    switch (dir) {
      case "up":    if (dy >= -1) continue; primary = -dy; perpendicular = Math.abs(dx); break;
      case "down":  if (dy <=  1) continue; primary =  dy; perpendicular = Math.abs(dx); break;
      case "left":  if (dx >= -1) continue; primary = -dx; perpendicular = Math.abs(dy); break;
      case "right": if (dx <=  1) continue; primary =  dx; perpendicular = Math.abs(dy); break;
    }
    const score = primary + perpendicular * 2;
    if (score < bestScore) {
      bestScore = score;
      best = el;
    }
  }
  return best;
}

function currentDirection(gp: Gamepad): Direction | null {
  if (gp.buttons[BTN_DPAD_UP]?.pressed) return "up";
  if (gp.buttons[BTN_DPAD_DOWN]?.pressed) return "down";
  if (gp.buttons[BTN_DPAD_LEFT]?.pressed) return "left";
  if (gp.buttons[BTN_DPAD_RIGHT]?.pressed) return "right";
  const [x, y] = gp.axes;
  if (y <= -STICK_DEADZONE) return "up";
  if (y >= STICK_DEADZONE) return "down";
  if (x <= -STICK_DEADZONE) return "left";
  if (x >= STICK_DEADZONE) return "right";
  return null;
}

// Global controller navigation (#476): D-pad/left-stick moves focus between
// the app's existing focusable elements, A clicks whatever's focused, X/Start
// launches the focused game card directly, B closes the topmost modal. Mount
// once at the app root.
export function useGamepadNav(): void {
  useEffect(() => {
    let rafId: number;
    let lastDirection: Direction | null = null;
    let nextMoveAt = 0;
    let prevA = false;
    let prevB = false;
    let prevX = false;
    let prevStart = false;
    // A text field only blocks D-pad navigation once explicitly "entered"
    // with A — landing on one via D-pad nav (it's just another focusable
    // element) must not trap the stick/D-pad there with no way back out.
    let editingInput: HTMLElement | null = null;
    // Last console/game card focused at the top level (no modal open) — restored
    // when a modal that covered it closes, so going into a game and backing out
    // returns focus to that same card instead of resetting to the first one.
    let lastCardFocus: HTMLElement | null = null;
    let wasInModal = false;

    function tick(): void {
      rafId = requestAnimationFrame(tick);
      // A gamepad's index is assigned by the browser in connection order and
      // is NOT guaranteed to be 0 — other HID devices that present a joystick-
      // shaped interface (e.g. some keyboard dongles) can occupy a lower slot
      // than the real controller. Standard Gamepad Mapping is what the button/
      // axis indices below assume, so require it explicitly rather than just
      // taking the first non-null slot — that also filters out those unrelated
      // non-gamepad devices, which report mapping "" (empty), not "standard".
      const gp = Array.from(navigator.getGamepads()).find((p): p is Gamepad => p !== null && p.mapping === "standard");
      if (!gp) return;

      const inModal = focusScope() !== document;
      if (inModal) {
        wasInModal = true;
      } else {
        if (wasInModal) {
          // Just closed: real focus drops to <body> if it had moved onto
          // something inside the modal (e.g. via D-pad nav while it was open).
          wasInModal = false;
          const el = document.activeElement as HTMLElement | null;
          if ((!el || el === document.body) && lastCardFocus && document.contains(lastCardFocus)) {
            lastCardFocus.focus();
          }
        }
        const el = document.activeElement as HTMLElement | null;
        if (el?.matches(".console-card, .game-card")) lastCardFocus = el;
      }

      const active = document.activeElement as HTMLElement | null;
      if (editingInput && active !== editingInput) editingInput = null; // focus moved by other means
      const isTextField = active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA");
      const editing = isTextField && active === editingInput;

      if (!editing) {
        const dir = currentDirection(gp);
        const now = performance.now();
        if (dir && dir !== lastDirection) {
          moveFocus(dir);
          nextMoveAt = now + REPEAT_INITIAL_DELAY_MS;
        } else if (dir && now >= nextMoveAt) {
          moveFocus(dir);
          nextMoveAt = now + REPEAT_INTERVAL_MS;
        }
        lastDirection = dir;
      }

      const aPressed = !!gp.buttons[BTN_A]?.pressed;
      if (aPressed && !prevA) {
        if (isTextField && !editing) editingInput = active; // enter edit mode, same as clicking into it
        else active?.click();
      }
      prevA = aPressed;

      // B backs out of an entered text field first, then mirrors Escape —
      // every modal already closes on Escape via useEscapeToClose/
      // useEscapeToCloseTopmost's own window keydown listeners (#474), so
      // dispatching a synthetic Escape keydown reuses that wiring for free
      // instead of duplicating close logic per modal.
      const bPressed = !!gp.buttons[BTN_B]?.pressed;
      if (bPressed && !prevB) {
        if (editing) {
          editingInput?.blur();
          editingInput = null;
        } else {
          window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
        }
      }
      prevB = bPressed;

      const xPressed = !!gp.buttons[BTN_X]?.pressed;
      const startPressed = !!gp.buttons[BTN_START]?.pressed;
      if ((xPressed && !prevX) || (startPressed && !prevStart)) launchFocusedGame(active);
      prevX = xPressed;
      prevStart = startPressed;
    }

    function moveFocus(dir: Direction): void {
      const active = document.activeElement as HTMLElement | null;
      const scope = focusScope();
      const inScope = active && active !== document.body && scope.contains(active);
      if (inScope) {
        findNextFocusable(active, dir)?.focus();
        return;
      }
      // Nothing focused yet: skip the topbar (Import/Conflicts/Server
      // buttons) and land on the first console/game card, not just the
      // first focusable thing in .content (GameGrid's search box sits
      // before the cards in DOM order and would otherwise win). Only
      // applies with no modal open — scope is the whole document then.
      const content = scope === document ? document.querySelector(".content") : null;
      const candidates = getFocusables();
      const first = content
        ? candidates.find((el) => content.contains(el) && el.matches(".console-card, .game-card"))
          ?? candidates.find((el) => content.contains(el))
        : candidates[0];
      first?.focus();
    }

    function launchFocusedGame(active: HTMLElement | null): void {
      const card = active?.closest<HTMLElement>(".game-card");
      const playBtn = card?.querySelector<HTMLButtonElement>(".game-card-btn-play");
      if (playBtn && !playBtn.disabled) playBtn.click();
    }

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, []);
}
