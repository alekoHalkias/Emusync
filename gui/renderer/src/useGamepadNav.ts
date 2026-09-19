import { useEffect } from "react";

// Standard Gamepad API mapping ("standard" gamepad_mapping) — Xbox-style
// layout, which is what Steam Input/SDL present Deck controls as too.
const BTN_A = 0;
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
// launches the focused game card directly. Mount once at the app root.
export function useGamepadNav(): void {
  useEffect(() => {
    let rafId: number;
    let lastDirection: Direction | null = null;
    let nextMoveAt = 0;
    let prevA = false;
    let prevX = false;
    let prevStart = false;

    function tick(): void {
      rafId = requestAnimationFrame(tick);
      const pads = navigator.getGamepads();
      const gp = pads[0];
      if (!gp) return;

      const active = document.activeElement as HTMLElement | null;
      const typing = active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA");

      if (!typing) {
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
      if (aPressed && !prevA) active?.click();
      prevA = aPressed;

      const xPressed = !!gp.buttons[BTN_X]?.pressed;
      const startPressed = !!gp.buttons[BTN_START]?.pressed;
      if ((xPressed && !prevX) || (startPressed && !prevStart)) launchFocusedGame(active);
      prevX = xPressed;
      prevStart = startPressed;
    }

    function moveFocus(dir: Direction): void {
      const active = document.activeElement as HTMLElement | null;
      const inScope = active && active !== document.body && focusScope().contains(active);
      const next = inScope ? findNextFocusable(active, dir) : getFocusables()[0];
      next?.focus();
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
