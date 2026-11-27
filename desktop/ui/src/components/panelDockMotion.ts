export type PanelBounds = { left: number; top: number; width: number; height: number };

const limit = (value: number, magnitude: number) => Math.max(-magnitude, Math.min(magnitude, value));

/** Motion for one held panel. The caller samples the latest pointer once per frame
 *  and keeps calling move with the same coordinates while the spring settles. */
export function createHeldPanelMotion(el: HTMLElement, startX: number, startY: number, bounds: PanelBounds, visible = bounds) {
  const style = el.style;
  const saved = { transform: style.transform, transformOrigin: style.transformOrigin,
    transition: style.transition, willChange: style.willChange, zIndex: style.zIndex };
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  const width = Math.max(1, bounds.width), height = Math.max(1, bounds.height);
  // A panel caught midway through a landing starts at the visible size and
  // keeps the same point under the pointer as it regains its natural size.
  const scaleX = Math.max(1, visible.width) / width, scaleY = Math.max(1, visible.height) / height;
  const gripX = Math.max(0, Math.min(width, (startX - visible.left) / scaleX));
  const gripY = Math.max(0, Math.min(height, (startY - visible.top) / scaleY));
  const offsetX = visible.left - bounds.left + gripX * (scaleX - 1);
  const offsetY = visible.top - bounds.top + gripY * (scaleY - 1);
  style.transformOrigin = `${gripX}px ${gripY}px`;
  style.transition = "none";
  style.willChange = "transform";
  style.zIndex = "40";
  if (offsetX || offsetY) style.transform = `translate3d(${offsetX}px, ${offsetY}px, 0)`;

  // An additive press composes after pointer translation, so the grip itself
  // stays under the cursor even when motion starts halfway through the press.
  const pressX = Math.min(.03, 8 / width), pressY = Math.min(.045, 10 / height);
  const press = media.matches ? undefined : el.animate([
    { transform: `scale(${scaleX}, ${scaleY})`, easing: "ease-out" },
    { offset: .33, transform: `scale(${1 + pressX}, ${1 - pressY})`, easing: "ease-in-out" },
    { offset: .74, transform: `scale(${1 - pressX * .3}, ${1 + pressY * .3})`, easing: "ease-out" },
    { transform: `scale(${1 + pressX * .2}, ${1 - pressY * .2})` },
  ], { duration: 260, composite: "add", fill: "forwards" });

  let lastX = startX, lastY = startY, lastTime: number | undefined;
  const horizontal = { bend: 0, speed: 0 }, vertical = { bend: 0, speed: 0 };
  // Bound deformation by screen pixels as well as angle/scale for wide panels.
  const maxTilt = Math.min(.037, 13 / Math.max(width, height));
  const stretchX = Math.min(.045, 13 / width), stretchY = Math.min(.045, 13 / height);
  let finished = false;

  return {
    move(x: number, y: number, time: number): boolean {
      if (finished) return false;
      const translate = `translate3d(${x - startX + offsetX}px, ${y - startY + offsetY}px, 0)`;
      if (media.matches) {
        press?.cancel();
        style.transform = translate;
        return false;
      }

      const ms = lastTime === undefined ? 1000 / 60 : Math.max(1, Math.min(64, time - lastTime));
      const dt = ms / 1000;
      // Closed-form damped spring for this interval. The response is consistent
      // across refresh rates and stays bounded if a frame arrives late.
      const decay = Math.exp(-15 * dt), cos = Math.cos(23 * dt), sin = Math.sin(23 * dt);
      const step = (axis: typeof horizontal, delta: number) => {
        const target = limit(delta / ms, 1);
        const offset = axis.bend - target;
        const wave = (axis.speed + 15 * offset) / 23;
        axis.bend = target + decay * (offset * cos + wave * sin);
        axis.speed = decay * (axis.speed * cos - (23 * offset + 15 * wave) * sin);
      };
      step(horizontal, x - lastX);
      step(vertical, y - lastY);
      lastX = x; lastY = y; lastTime = time;
      const energy = Math.max(Math.abs(horizontal.bend), Math.abs(vertical.bend),
        Math.abs(horizontal.speed) / 23, Math.abs(vertical.speed) / 23);
      if (energy < .003) {
        horizontal.bend = horizontal.speed = vertical.bend = vertical.speed = 0;
        style.transform = translate;
        return false;
      }

      const stretch = limit(Math.abs(horizontal.bend) - Math.abs(vertical.bend), 1);
      const tilt = limit(horizontal.bend + vertical.bend * (gripX / width - .5), 1) * maxTilt;
      style.transform = `${translate} rotate(${tilt}rad) scale(${1 + stretch * stretchX}, ${1 - stretch * stretchY})`;
      return true;
    },
    finish() {
      if (finished) return;
      finished = true;
      press?.cancel();
      Object.assign(style, saved);
    },
  };
}

/** The caller has already applied the destination layout. Start at the panel's
 *  previous visible bounds and let the compositor carry it into its new slot. */
export function animatePanelDock(el: HTMLElement, from: PanelBounds, to: PanelBounds, landing = false): Animation | undefined {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (Math.min(from.width, from.height, to.width, to.height) <= 0) return;

  const dw = from.width - to.width, dh = from.height - to.height;
  const dx = from.left - to.left + dw / 2, dy = from.top - to.top + dh / 2;
  if (Math.max(Math.abs(dx), Math.abs(dy), Math.abs(dw), Math.abs(dh)) < .25) return;

  // Displace the center independently of the squash; a wide panel should
  // compress around its middle without kicking its far edge across the screen.
  const pose = (cx: number, cy: number, w: number, h: number) =>
    `translate3d(${cx - w / 2}px, ${cy - h / 2}px, 0) scale(${1 + w / to.width}, ${1 + h / to.height})`;
  const impact = limit((Math.abs(dx) - Math.abs(dy)) * .00045, .04);
  const squashW = limit(-dw * .06 - impact * to.width, Math.min(10, to.width * .045));
  const squashH = limit(-dh * .06 + impact * to.height, Math.min(10, to.height * .045));
  const bounceX = limit(-dx * .055, Math.min(9, to.width * .05));
  const bounceY = limit(-dy * .055, Math.min(9, to.height * .05));

  return el.animate([
    { offset: 0, transform: pose(dx, dy, dw, dh), easing: "cubic-bezier(.2,.72,.32,1)" },
    { offset: .56, transform: pose(bounceX, bounceY, squashW, squashH), easing: "ease-in-out" },
    { offset: .79, transform: pose(-bounceX * .24, -bounceY * .24, -squashW * .3, -squashH * .3), easing: "ease-out" },
    { offset: 1, transform: "none" },
  ].map(frame => ({ ...frame, transformOrigin: "0 0", ...(landing && { zIndex: 40 }) })), { duration: 360 });
}
