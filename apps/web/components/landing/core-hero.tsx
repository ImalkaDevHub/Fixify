"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { CSSProperties, MouseEvent, PointerEvent as ReactPointerEvent, ReactElement, ReactNode, SVGProps } from "react";
import { AnimatePresence, LazyMotion, animate, domAnimation, m, useInView, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import type { MotionValue } from "motion/react";
import Link from "next/link";
import { ArrowRight, Bug, Cable, FilePen, GitPullRequest, Menu, MousePointer2, ShieldCheck, UserCheck, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { LogoMark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";

/**
 * An isometric "exploded core" hero: a three-layer ceramic stack that separates into five stage
 * plates on hover, each paired with a floating card describing that stage of the Fixify
 * pipeline. Adapted from a MotionUIKit block; fonts/colors are swapped for the project's own
 * (no external font fetch — the CSP only allows self-hosted fonts), and all copy, stages, and
 * logos reflect what Fixify actually does rather than the block's original generic SaaS content.
 */

const BLOCK_CSS = `
:root {
  /* Aliased to the app's real design tokens (app/globals.css) instead of fixed hex, so the
     background/text/accent/border here follow the global theme toggle. The frosted-glass stage
     cards, nav-scrolled backdrop, and the 3D core's own ceramic/crystal material below are a
     fixed light "product render" treatment, left as-is — fully re-theming those is a presentation
     change for a later pass, not attempted here. */
  --color-n3-page: var(--color-canvas);
  --color-n3-ink: var(--color-ink);
  --color-n3-grey: var(--color-muted);
  --color-n3-line: var(--color-line);
  --color-n3-accent: var(--color-violet);
  --font-n3-sans: var(--font-sans);
}

.n3-root {
  --n3-gutter: 20px;
  --n3-nav-space: 76px;
}

@media (min-width: 640px) {
  .n3-root {
    --n3-gutter: 32px;
  }
}

@media (min-width: 1024px) {
  .n3-root {
    --n3-gutter: 56px;
  }
}

.n3-frame {
  padding-left: var(--n3-gutter);
  padding-right: var(--n3-gutter);
}

.n3-hero {
  min-height: calc(100dvh - var(--n3-nav-space));
}

@media (max-width: 1023px) {
  .n3-hero {
    min-height: 0;
  }
}

.n3-h1 {
  font-size: clamp(2.5rem, 1.1rem + 3.6vw, 4.35rem);
  line-height: 1.06;
  letter-spacing: -0.035em;
}

.n3-bg {
  background:
    radial-gradient(ellipse 60% 70% at 74% 52%, rgb(255 255 255 / 0.95) 0%, rgb(255 255 255 / 0) 70%),
    radial-gradient(ellipse 40% 45% at 78% 58%, rgb(124 58 237 / 0.07) 0%, rgb(124 58 237 / 0) 70%),
    radial-gradient(ellipse 50% 40% at 100% 0%, rgb(233 230 223 / 0.7) 0%, rgb(233 230 223 / 0) 70%),
    var(--color-n3-page);
}

/* Same composition as .n3-bg (identical ellipse positions/sizes): the light-paper highlight wash
   recolored as a dark-canvas violet glow, matching the rest of the app's .ambient treatment. */
[data-theme="dark"] .n3-bg {
  background:
    radial-gradient(ellipse 60% 70% at 74% 52%, rgb(167 139 250 / 0.16) 0%, rgb(167 139 250 / 0) 70%),
    radial-gradient(ellipse 40% 45% at 78% 58%, rgb(124 58 237 / 0.12) 0%, rgb(124 58 237 / 0) 70%),
    radial-gradient(ellipse 50% 40% at 100% 0%, rgb(34 34 40 / 0.8) 0%, rgb(34 34 40 / 0) 70%),
    var(--color-n3-page);
}

.n3-halo {
  border-radius: 9999px;
  background: radial-gradient(closest-side, rgb(255 255 255 / 0.9), rgb(255 255 255 / 0));
}

.n3-floor,
.n3-floor-lit {
  --n3-floor-area: radial-gradient(ellipse 75% 80% at 72% 70%, #000 20%, transparent 100%);
  --n3-floor-edges:
    linear-gradient(to left, transparent 0%, #000 22%), linear-gradient(to top, transparent 0%, #000 28%);

  -webkit-mask-image: var(--n3-floor-area), var(--n3-floor-edges);
  mask-image: var(--n3-floor-area), var(--n3-floor-edges);
  -webkit-mask-composite: source-in;
  mask-composite: intersect;
}

.n3-floor {
  opacity: 0.35;
}

.n3-floor-spot {
  position: absolute;
  top: 0;
  left: 0;
  opacity: 0;
  transition: opacity 400ms ease;
  will-change: transform, opacity;
  -webkit-mask-image: radial-gradient(closest-side, #000 0%, transparent 100%);
  mask-image: radial-gradient(closest-side, #000 0%, transparent 100%);
}

.n3-floor-lit {
  position: absolute;
  top: 0;
  left: 0;
  will-change: transform;
}

[data-spot='on'] > .n3-floor-spot {
  opacity: 0.7;
}

@media (max-width: 1023px) {
  .n3-floor,
  .n3-floor-lit {
    --n3-floor-area: radial-gradient(ellipse 90% 60% at 50% 75%, #000 20%, transparent 100%);
  }
}

.n3-fade-edge {
  -webkit-mask-image: linear-gradient(to right, transparent 0%, #000 14%);
  mask-image: linear-gradient(to right, transparent 0%, #000 14%);
}

@media (max-width: 1023px) {
  .n3-fade-edge {
    -webkit-mask-image: none;
    mask-image: none;
  }
}

.n3-nav-bar {
  border-bottom: 1px solid transparent;
  transition:
    background-color 300ms ease,
    border-color 300ms ease;
}

.n3-nav-bar-scrolled {
  background-color: rgb(248 247 243 / 0.78);
  border-bottom-color: rgb(23 23 23 / 0.06);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
}

[data-theme="dark"] .n3-nav-bar-scrolled {
  background-color: rgb(17 17 20 / 0.78);
  border-bottom-color: rgb(245 245 245 / 0.08);
}

.n3-flip {
  perspective: 600px;
}

.n3-flip-box {
  --d: 0.75em;
  display: inline-grid;
  transform-style: preserve-3d;
  transform: translateZ(calc(var(--d) * -1)) rotateX(0deg);
  transition: transform 550ms cubic-bezier(0.22, 1, 0.36, 1);
}

.n3-flip-face {
  grid-area: 1 / 1;
  display: inline-flex;
  height: 1.5em;
  align-items: center;
  justify-content: center;
  line-height: 1.5em;
  backface-visibility: hidden;
  transform: translateZ(var(--d));
}

.n3-flip-back {
  transform: rotateX(-90deg) translateZ(var(--d));
}

.n3-flip:hover .n3-flip-box,
.n3-flip:focus-visible .n3-flip-box {
  transform: translateZ(calc(var(--d) * -1)) rotateX(90deg);
}

@media (prefers-reduced-motion: reduce) {
  .n3-flip-box {
    transition: none;
  }

  .n3-flip:hover .n3-flip-box,
  .n3-flip:focus-visible .n3-flip-box {
    transform: translateZ(calc(var(--d) * -1));
  }
}

.n3-dot {
  box-shadow: 0 0 0 4px rgb(124 58 237 / 0.14);
}

.n3-rise {
  animation: n3-rise 700ms cubic-bezier(0.22, 1, 0.36, 1) backwards;
}

.n3-drop {
  animation: n3-drop 600ms cubic-bezier(0.22, 1, 0.36, 1) backwards;
}

.n3-enter {
  animation: n3-enter 1100ms cubic-bezier(0.22, 1, 0.36, 1) 250ms backwards;
}

@keyframes n3-rise {
  from {
    opacity: 0;
    translate: 0 18px;
  }
}

@keyframes n3-drop {
  from {
    opacity: 0;
    translate: 0 -12px;
  }
}

@keyframes n3-enter {
  from {
    opacity: 0;
    scale: 0.97;
  }
}

@media (prefers-reduced-motion: reduce) {
  .n3-rise,
  .n3-drop,
  .n3-enter {
    animation: none;
  }
}

@keyframes n3-float {
  from {
    transform: translateY(0);
  }
  to {
    transform: translateY(calc(var(--n3-float, 6) * -1px));
  }
}

.n3-float {
  animation: n3-float var(--n3-float-seconds, 6.5s) ease-in-out infinite alternate;
}

@keyframes n3-seam {
  from {
    opacity: 0.78;
  }
  to {
    opacity: 1;
  }
}

.n3-seam-pulse {
  animation: n3-seam 4.8s ease-in-out infinite alternate;
}

@media (prefers-reduced-motion: reduce) {
  .n3-float,
  .n3-seam-pulse {
    animation: none;
  }
}

.n3-stage-card {
  border: 1px solid rgb(23 23 23 / 0.06);
  border-radius: 1.3em;
  background: rgb(255 255 255 / 0.82);
  box-shadow:
    0 1px 2px rgb(60 50 40 / 0.04),
    0 14px 34px -18px rgb(90 78 62 / 0.3),
    inset 0 1px 0 rgb(255 255 255 / 0.9);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  transition:
    border-color 300ms ease,
    box-shadow 300ms ease;
}

.n3-stage-card-lit {
  border-color: rgb(124 58 237 / 0.35);
  box-shadow:
    0 1px 2px rgb(60 50 40 / 0.04),
    0 18px 38px -18px rgb(124 58 237 / 0.4),
    inset 0 1px 0 rgb(255 255 255 / 0.9);
}

[data-theme="dark"] .n3-stage-card {
  border-color: rgb(245 245 245 / 0.08);
  background: rgb(27 27 33 / 0.86);
  box-shadow:
    0 1px 2px rgb(0 0 0 / 0.2),
    0 14px 34px -18px rgb(0 0 0 / 0.55),
    inset 0 1px 0 rgb(245 245 245 / 0.06);
}

[data-theme="dark"] .n3-stage-card-lit {
  border-color: rgb(167 139 250 / 0.4);
  box-shadow:
    0 1px 2px rgb(0 0 0 / 0.2),
    0 18px 38px -18px rgb(167 139 250 / 0.45),
    inset 0 1px 0 rgb(245 245 245 / 0.06);
}

@container (max-width: 640px) {
  .n3-stage-apps {
    display: none;
  }
}
`;

// ───── geometry: shared isometric projection for every slab, orbit, and card on the core ─────

const ISO_X = 0.866;
const ISO_Y = 0.5;

const CX = 500;
const CY = 500;

const RING_FLATTEN = 0.57;
const RING_RX = [400, 530] as const;

type SlabType = {
  half: number;
  radius: number;
  top: number;
  depth: number;
};

const BASE: SlabType = { half: 168, radius: 40, top: 475, depth: 34 };
const SEAM_GAP = 9;
const MID: SlabType = { half: 151, radius: 36, top: BASE.top - SEAM_GAP - 28, depth: 28 };
const CAP: SlabType = { half: 101, radius: 28, top: MID.top - 14, depth: 14 };

type Point = [number, number];

const round = (n: number) => Math.round(n * 100) / 100;

const project = (x: number, y: number, cx = CX, cy = CY): Point => {
  return [cx + (x - y) * ISO_X, cy + (x + y) * ISO_Y];
};

const footprint = (half: number, radius: number, steps = 14): Point[] => {
  const r = Math.min(radius, half);
  const c = half - r;

  const corners: [number, number, number][] = [
    [c, c, 0],
    [-c, c, 90],
    [-c, -c, 180],
    [c, -c, 270],
  ];

  const pts: Point[] = [];

  for (const [ox, oy, start] of corners) {
    for (let i = 0; i <= steps; i++) {
      const a = ((start + (90 * i) / steps) * Math.PI) / 180;

      pts.push([ox + r * Math.cos(a), oy + r * Math.sin(a)]);
    }
  }

  return pts;
};

const toPath = (pts: Point[]) => `M${pts.map(([x, y]) => `${x.toFixed(2)} ${y.toFixed(2)}`).join("L")}Z`;

const topPath = (slab: SlabType, inset = 0, cx = CX, dy = 0) => {
  const half = slab.half - inset;
  const radius = Math.max(slab.radius - inset, 1);

  return toPath(footprint(half, radius).map(([x, y]) => project(x, y, cx, slab.top + dy)));
};

const hull = (points: Point[]): Point[] => {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: Point, a: Point, b: Point) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);

  const build = (list: Point[]) => {
    const out: Point[] = [];

    for (const p of list) {
      while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], p) <= 0) out.pop();
      out.push(p);
    }

    out.pop();

    return out;
  };

  return [...build(pts), ...build([...pts].reverse())];
};

const bodyPath = (slab: SlabType, inset = 0) => {
  const half = slab.half - inset;
  const radius = Math.max(slab.radius - inset, 1);
  const outline = footprint(half, radius);
  const upper = outline.map(([x, y]) => project(x, y, CX, slab.top));
  const lower = outline.map(([x, y]) => project(x, y, CX, slab.top + slab.depth));

  return toPath(hull([...upper, ...lower]));
};

const facePoint = (slab: SlabType, side: "left" | "right", u: number, v: number): Point => {
  const { half, top, depth } = slab;

  if (side === "left") {
    const [x, y] = project(-half + 2 * half * u, half, CX, top);

    return [x, y + depth * v];
  }

  const [x, y] = project(half, half - 2 * half * u, CX, top);

  return [x, y + depth * v];
};

const FACE_MATRIX = {
  left: `${ISO_X} ${ISO_Y} 0 1`,
  right: `${ISO_X} ${-ISO_Y} 0 1`,
  top: `${ISO_X} ${ISO_Y} ${-ISO_X} ${ISO_Y}`,
};

const ringPoint = (rx: number, angleDeg: number): Point => {
  const a = (angleDeg * Math.PI) / 180;

  return [round(CX + rx * Math.cos(a)), round(CY + rx * RING_FLATTEN * Math.sin(a))];
};

const ringPath = (rx: number) => {
  const ry = rx * RING_FLATTEN;

  return `M${CX + rx} ${CY}A${rx} ${ry} 0 1 1 ${CX - rx} ${CY}A${rx} ${ry} 0 1 1 ${CX + rx} ${CY}Z`;
};

// ───── the mark: four leaves turned a quarter each — an abstract ornament inlaid on the core ─────

const LEAF = "M11 0H19A3 3 0 0 1 22 3V11A11 11 0 0 1 11 22H3A3 3 0 0 1 0 19V11A11 11 0 0 1 11 0Z";

const TURNS = [0, 90, 180, 270];
const OPACITY = [1, 0.9, 0.8, 0.9];

type LeavesProps = { fill: string; fades?: boolean; stroke?: string };

const Leaves = ({ fill, fades = false, stroke }: LeavesProps) => {
  return (
    <>
      {TURNS.map((turn, i) => (
        <path
          key={turn}
          d={LEAF}
          transform={`rotate(${turn}) translate(-25 -25)`}
          fill={fill}
          stroke={stroke}
          strokeWidth={stroke ? 0.6 : undefined}
          opacity={fades ? OPACITY[i] : 1}
        />
      ))}
    </>
  );
};

// ───── the core's parts: slabs, faces, fasteners, and the inlaid mark ─────

const ACCENT = "#7C3AED";

type FaceProps = { slab: SlabType; side: "left" | "right"; u: number; v: number };

const FaceMark = ({
  slab,
  side,
  u,
  v,
  w,
  h,
  fill,
  glow,
}: FaceProps & { w: number; h: number; fill: string; glow?: boolean }) => {
  const [x, y] = facePoint(slab, side, u, v);

  return (
    <g transform={`translate(${x.toFixed(2)} ${y.toFixed(2)}) matrix(${FACE_MATRIX[side]} 0 0)`}>
      {glow && (
        <rect
          x={-w / 2 - 2}
          y={-h / 2 - 3}
          width={w + 4}
          height={h + 6}
          rx={h}
          fill={fill}
          filter="url(#n3-blur-sm)"
          opacity="0.75"
        />
      )}
      <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={h / 2} fill={fill} />
    </g>
  );
};

type PanelLineProps = {
  slab: SlabType;
  side: "left" | "right";
  v: number;
  from?: number;
  to?: number;
};

const PanelLine = ({ slab, side, v, from = 0.14, to = 0.86 }: PanelLineProps) => {
  const [x1, y1] = facePoint(slab, side, from, v);
  const [x2, y2] = facePoint(slab, side, to, v);

  return <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#A7A298" strokeWidth="0.9" opacity="0.55" />;
};

type FastenerProps = { slab: SlabType; x: number; y: number };

const Fastener = ({ slab, x, y }: FastenerProps) => {
  const [px, py] = project(x, y, CX, slab.top);

  return (
    <g transform={`translate(${px.toFixed(2)} ${py.toFixed(2)}) matrix(${FACE_MATRIX.top} 0 0)`}>
      <circle r="6.5" fill="url(#n3-hole)" stroke="#C9C5BB" strokeWidth="1" />
    </g>
  );
};

const SlabBody = ({ slab }: { slab: SlabType }) => {
  return (
    <g>
      <path d={bodyPath(slab)} fill="url(#n3-side)" />
      <path d={bodyPath(slab)} fill="url(#n3-side-shade)" />
      <path d={bodyPath(slab)} fill="none" stroke="#CFCBC1" strokeWidth="1" opacity="0.85" />
    </g>
  );
};

const SlabTop = ({ slab, groove }: { slab: SlabType; groove?: number }) => {
  return (
    <g>
      <path d={topPath(slab)} fill="url(#n3-bevel)" stroke="#D9D6D0" strokeWidth="1" />
      <path d={topPath(slab, 4.5)} fill="url(#n3-top)" stroke="#fff" strokeWidth="1" opacity="1" />
      {groove !== undefined && <path d={topPath(slab, groove)} fill="none" stroke="#DAD6CE" strokeWidth="1.2" />}
    </g>
  );
};

const LOGO_SIDE = ["#4C1D95", "#5B21B6", "#6D28D9", "#7C3AED", "#8B5CF6", "#A78BFA"];
const LOGO_SCALE = 1.42;

const CoreLogo = ({ x, y }: { x: number; y: number }) => {
  const plane = (lift: number) => `translate(${x} ${y - lift}) matrix(${FACE_MATRIX.top} 0 0) scale(${LOGO_SCALE})`;
  const top = LOGO_SIDE.length;

  return (
    <g>
      <g transform={`${plane(0)} translate(2.4 2.4)`} opacity="0.22" filter="url(#n3-blur-sm)">
        <Leaves fill="#6E6556" />
      </g>
      {LOGO_SIDE.map((fill, k) => (
        <g key={fill} transform={plane(k)}>
          <Leaves fill={fill} />
        </g>
      ))}
      <g transform={plane(top)}>
        <rect x="-27" y="-27" width="54" height="54" fill="url(#n3-logo-top)" clipPath="url(#n3-mark-clip)" />
        <Leaves fill="none" stroke="#DDD6FE" />
      </g>
    </g>
  );
};

const CoreDefs = () => {
  return (
    <defs>
      <linearGradient id="n3-side" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#F3F1EB" />
        <stop offset="0.46" stopColor="#E9E6DF" />
        <stop offset="0.5" stopColor="#DAD6CD" />
        <stop offset="1" stopColor="#E3DFD7" />
      </linearGradient>
      <linearGradient id="n3-side-shade" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0.45" stopColor="#7C7566" stopOpacity="0" />
        <stop offset="1" stopColor="#7C7566" stopOpacity="0.16" />
      </linearGradient>
      <linearGradient id="n3-bevel" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#FFFFFF" />
        <stop offset="1" stopColor="#E6E2DA" />
      </linearGradient>
      <linearGradient id="n3-top" x1="0.1" y1="0" x2="0.9" y2="1">
        <stop offset="0" stopColor="#FFFFFF" />
        <stop offset="1" stopColor="#F2EFE9" />
      </linearGradient>
      <linearGradient id="n3-inlay" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#EFEBE4" />
        <stop offset="1" stopColor="#FFFFFF" />
      </linearGradient>
      <linearGradient id="n3-seam" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="#C4B5FD" />
        <stop offset="0.5" stopColor={ACCENT} />
        <stop offset="1" stopColor="#A78BFA" />
      </linearGradient>
      <linearGradient id="n3-slot" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor="#5F5A52" />
        <stop offset="1" stopColor="#8E897F" />
      </linearGradient>
      <linearGradient id="n3-logo-top" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#C4B5FD" />
        <stop offset="0.55" stopColor="#8B5CF6" />
        <stop offset="1" stopColor="#6D28D9" />
      </linearGradient>
      <clipPath id="n3-mark-clip">
        <Leaves fill="#000" />
      </clipPath>
      <radialGradient id="n3-hole" cx="0.5" cy="0.4" r="0.7">
        <stop offset="0" stopColor="#D9D5CC" />
        <stop offset="1" stopColor="#F3F1EB" />
      </radialGradient>
      <filter id="n3-blur-sm" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="3.5" />
      </filter>
      <filter id="n3-blur-glow" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="9" />
      </filter>
      <filter id="n3-blur-spill" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="18" />
      </filter>
    </defs>
  );
};

const CoreObject = (props: SVGProps<SVGSVGElement>) => {
  const seam: SlabType = {
    half: MID.half - 2,
    radius: MID.radius - 2,
    top: MID.top + MID.depth - 1,
    depth: SEAM_GAP + 1,
  };

  const spillDy = BASE.top - MID.top;
  const [logoX, logoY] = [CX, CAP.top];

  return (
    <svg viewBox="0 0 1000 1000" role="img" aria-label="The Fixify core" {...props}>
      <CoreDefs />

      <SlabBody slab={BASE} />
      <SlabTop slab={BASE} groove={10} />
      <PanelLine slab={BASE} side="left" v={0.3} />
      <PanelLine slab={BASE} side="right" v={0.3} />
      <FaceMark slab={BASE} side="right" u={0.5} v={0.62} w={4.5} h={4.5} fill="url(#n3-slot)" />
      <FaceMark slab={BASE} side="right" u={0.58} v={0.62} w={4.5} h={4.5} fill="url(#n3-slot)" />
      <FaceMark slab={BASE} side="right" u={0.66} v={0.62} w={4.5} h={4.5} fill="url(#n3-slot)" />
      <FaceMark slab={BASE} side="left" u={0.32} v={0.62} w={4.5} h={4.5} fill="url(#n3-slot)" />
      <FaceMark slab={BASE} side="left" u={0.4} v={0.62} w={4.5} h={4.5} fill="url(#n3-slot)" />

      <g className="n3-seam-pulse">
        <path d={topPath(MID, 4, CX, spillDy)} fill={ACCENT} opacity="0.24" filter="url(#n3-blur-spill)" />
        <path d={bodyPath(seam)} fill={ACCENT} opacity="0.6" filter="url(#n3-blur-glow)" />
      </g>
      <path d={bodyPath(seam)} fill="url(#n3-seam)" />

      <SlabBody slab={MID} />
      <SlabTop slab={MID} groove={11} />
      <PanelLine slab={MID} side="left" v={0.78} />
      <PanelLine slab={MID} side="right" v={0.78} />
      <FaceMark slab={MID} side="left" u={0.62} v={0.42} w={34} h={7.5} fill="url(#n3-slot)" />
      <FaceMark slab={MID} side="left" u={0.34} v={0.42} w={5} h={5} fill="url(#n3-slot)" />
      <FaceMark slab={MID} side="left" u={0.42} v={0.42} w={5} h={5} fill="url(#n3-slot)" />
      <FaceMark slab={MID} side="right" u={0.44} v={0.42} w={5} h={5} fill="url(#n3-slot)" />
      <FaceMark slab={MID} side="right" u={0.52} v={0.42} w={5} h={5} fill="url(#n3-slot)" />
      <FaceMark slab={MID} side="right" u={0.68} v={0.42} w={22} h={4.5} fill="url(#n3-slot)" />
      <g className="n3-seam-pulse">
        <FaceMark slab={MID} side="left" u={0.2} v={0.42} w={7} h={2.6} fill={ACCENT} glow />
      </g>

      <Fastener slab={MID} x={0} y={-MID.half + 28} />
      <Fastener slab={MID} x={-MID.half + 28} y={0} />
      <Fastener slab={MID} x={MID.half - 28} y={0} />
      <Fastener slab={MID} x={0} y={MID.half - 28} />

      <SlabBody slab={CAP} />
      <SlabTop slab={CAP} />
      <path d={topPath(CAP, 19)} fill="url(#n3-inlay)" stroke="#DDD9D1" strokeWidth="1.2" />
      <path d={topPath(CAP, 20.5)} fill="none" stroke="#fff" strokeWidth="1" opacity="0.9" />

      <CoreLogo x={logoX} y={logoY} />
    </svg>
  );
};

const CoreShadow = (props: SVGProps<SVGSVGElement>) => {
  const floor = { ...BASE, top: BASE.top + BASE.depth + 30 };

  return (
    <svg viewBox="0 0 1000 1000" aria-hidden {...props}>
      <defs>
        <filter id="n3-blur-lg" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="26" />
        </filter>
        <filter id="n3-blur-md" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="9" />
        </filter>
      </defs>
      <path d={topPath(floor, -14)} fill="#8A8377" opacity="0.2" filter="url(#n3-blur-lg)" />
      <path d={topPath(floor, 6)} fill="#5D574D" opacity="0.22" filter="url(#n3-blur-md)" />
    </svg>
  );
};

const NODES: [number, number][] = [
  [118, 132],
  [318, 82],
  [690, 96],
  [884, 188],
  [936, 470],
  [70, 512],
  [150, 858],
  [850, 846],
];

const DepthBackdrop = (props: SVGProps<SVGSVGElement>) => {
  return (
    <svg viewBox="0 0 1000 1000" aria-hidden {...props}>
      <defs>
        <linearGradient id="n3-glass" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.7" />
          <stop offset="1" stopColor="#fff" stopOpacity="0.12" />
        </linearGradient>
      </defs>

      <g fill="url(#n3-glass)" stroke="#E3E0D9" strokeWidth="1" opacity="0.35">
        <rect width="290" height="250" rx="22" transform="matrix(0.866 -0.5 0 1 232 300)" />
        <rect width="290" height="250" rx="22" transform="matrix(0.866 0.5 0 1 520 150)" />
      </g>

      <g fill="#fff" stroke="#CFCBC1" strokeWidth="1">
        {NODES.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={i % 3 === 0 ? 4 : 3} opacity="0.85" />
        ))}
      </g>
    </svg>
  );
};

// ───── copy, nav, and pipeline-stage content (Fixify's own, not the template's placeholder) ─────

const EASE = [0.22, 1, 0.36, 1] as const;

const COPY = {
  headline: ["Find Bugs.", "Understand Them.", "Fix Them."],
  accentLine: "Understand Them.",
  body: "An intelligent website testing platform that detects real-world issues, explains what went wrong, and helps your team generate human-reviewed fixes.",
  primaryCta: "Start Testing",
  primaryCtaHref: "/register",
  secondaryCta: "Explore Features",
  secondaryCtaHref: "#how",
};

const NAV_LINKS = [
  { label: "How it works", href: "#how" },
  { label: "Scanning", href: "#scanning" },
  { label: "AI analysis", href: "#ai" },
  { label: "GitHub", href: "#github" },
  { label: "Security", href: "#security" },
];

const ICONS = { bug: Bug, shield: ShieldCheck, pr: GitPullRequest };

const METRICS = [
  { value: "9+", label: "Automated checks per scan", icon: "bug" },
  { value: "100%", label: "Human-reviewed before any PR", icon: "shield" },
  { value: "0", label: "Pull requests without your approval", icon: "pr" },
] as const;

const MOTION = {
  floatDistance: 10,
  floatSeconds: 6.5,
  tiltDegrees: 3.5,
  ringParallax: 12,
  backdropParallax: 5,
  orbitSeconds: [70, 95],
  orbitOpenOpacity: 0.15,
};

const ARTBOARD = 1000;

/**
 * The exploded view, bottom to top: evidence comes in at the bottom plate, a pull request leaves
 * at the top. GitHub and the two AI providers Fixify actually supports (app/ai/provider.py) are
 * the only brand logos shown — no fabricated integrations.
 */
const STAGES = [
  {
    title: "Website Scan",
    items: ["Navigation & console", "Broken links & images", "Screenshot evidence"],
    apps: [],
    icon: "sources",
    side: "right",
  },
  {
    title: "Repository Context",
    items: ["Allow-listed files", "Existing code", "Reviewer notes"],
    apps: ["GitHub"],
    icon: "context",
    side: "left",
  },
  {
    title: "AI Intelligence",
    items: ["Root cause & impact", "Confidence & evidence", "Fix proposal"],
    apps: ["Gemini", "Claude"],
    side: "right",
    main: true,
  },
  {
    title: "Human Review",
    items: ["Side-by-side diff", "Approve or reject", "Regenerate with feedback"],
    apps: [],
    icon: "review",
    side: "left",
  },
  {
    title: "Pull Request",
    items: ["New branch", "Diff you approved", "Never auto-merged"],
    apps: ["GitHub"],
    icon: "outcomes",
    side: "right",
  },
] as const;

type Stage = (typeof STAGES)[number];

const isMain = (stage: Stage) => "main" in stage && stage.main;

const EXPLODE = {
  spring: { stiffness: 105, damping: 25, mass: 1 },
  gap: 94,
  aiLift: 12,
  topPlateY: 230,
  stagger: 0.05,
  scales: [0.63, 0.62, 0.7, 1.07, 1.06],
};

const STAGE_CARDS = {
  left: { edge: -2, width: 31 },
  right: { edge: 0, width: 29 },
  restInset: 10,
  outward: 2,
  beadSeconds: 1.6,
};

// ───── the plates: cut from the three stacked slabs so they match the resting object exactly ─────

const PLATE_SLABS: SlabType[] = [
  { ...BASE, top: BASE.top + 17, depth: 17 },
  { ...BASE, top: BASE.top, depth: 17 },
  MID,
  { ...CAP, top: CAP.top + 7, depth: 7 },
  { ...CAP, top: CAP.top, depth: 7 },
];

const AI_PLATE = 2;

const TARGET_TOPS = PLATE_SLABS.map(
  (_, i) => EXPLODE.topPlateY + (PLATE_SLABS.length - 1 - i) * EXPLODE.gap - (i === AI_PLATE ? EXPLODE.aiLift : 0)
);

const TRAVEL = PLATE_SLABS.map((slab, i) => TARGET_TOPS[i] - slab.top);

const clamp = (v: number) => Math.min(1, Math.max(0, v));

const plateProgress = (i: number, p: number) => {
  const delay = Math.abs(i - AI_PLATE) * EXPLODE.stagger;

  return clamp((p - delay) / (1 - delay));
};

const plateY = (i: number, p: number) => TRAVEL[i] * plateProgress(i, p);
const plateScale = (i: number, p: number) => 1 + (EXPLODE.scales[i] - 1) * plateProgress(i, p);

const tipOffset = (i: number) => {
  const { half, radius } = PLATE_SLABS[i];

  return 0.866 * (2 * half - 0.586 * radius) * EXPLODE.scales[i];
};

const tipX = (i: number, side: "left" | "right") => CX + (side === "right" ? 1 : -1) * tipOffset(i);
const cornerY = (i: number) => TARGET_TOPS[i] + PLATE_SLABS[i].depth / 2;

const clamp2 = (v: number) => Math.min(1, Math.max(0, v));

const SKIRT = [0, 4, 0, 10, 10];

type PlateProps = {
  index: number;
  progress: MotionValue<number>;
  children: ReactNode;
};

const Plate = ({ index, progress, children }: PlateProps) => {
  const y = useTransform(progress, (v) => plateY(index, v));
  const scale = useTransform(progress, (v) => plateScale(index, v));
  const apart = useTransform(progress, (v) => plateProgress(index, v));
  const shadow = useTransform(apart, (v) => v * 0.16);

  const slab = PLATE_SLABS[index];
  const skirt = SKIRT[index];

  return (
    <m.g style={{ y, scale }}>
      {index > 0 && (
        <m.path
          d={topPath(slab, -6, CX, slab.depth + 34)}
          fill="#6E6556"
          filter="url(#n3-blur-spill)"
          style={{ opacity: shadow }}
        />
      )}
      {skirt > 0 && (
        <m.g style={{ opacity: apart }}>
          <SlabBody slab={{ ...slab, top: slab.top + slab.depth - 1, depth: skirt + 1 }} />
        </m.g>
      )}
      {children}
    </m.g>
  );
};

type PlateNumberProps = { slab: SlabType; n: number; main?: boolean };

const PlateNumber = ({ slab, n, main = false }: PlateNumberProps) => {
  const k = slab.half * 0.56;
  const [x, y] = project(k, k, CX, slab.top);
  const plane = `matrix(${FACE_MATRIX.top} 0 0) rotate(-45)`;
  const label = String(n).padStart(2, "0");

  const text = {
    textAnchor: "middle" as const,
    dominantBaseline: "central" as const,
    fontSize: 25,
    fontWeight: 500,
    letterSpacing: 2.5,
  };

  return (
    <g transform={`translate(${x.toFixed(2)} ${y.toFixed(2)})`} aria-hidden>
      <text {...text} transform={`translate(0 0.9) ${plane}`} fill="#FFFFFF" opacity="0.95">
        {label}
      </text>
      <text {...text} transform={plane} fill={main ? "#8B5CF6" : "#CBC6BC"}>
        {label}
      </text>
    </g>
  );
};

const AiEmphasis = ({ progress }: { progress: MotionValue<number> }) => {
  const on = useTransform(progress, (v) => clamp2((v - 0.5) / 0.4));
  const rim = useTransform(on, (v) => v * 0.9);
  const halo = useTransform(on, (v) => v * 0.55);
  const spill = useTransform(halo, (v) => v * 0.35);

  return (
    <g transform={`translate(${CX} ${MID.top}) matrix(${FACE_MATRIX.top} 0 0)`}>
      <m.circle r="86" fill={ACCENT} filter="url(#n3-blur-spill)" style={{ opacity: spill }} />
      <m.circle r="56" fill="none" stroke={ACCENT} strokeWidth="1.4" style={{ opacity: rim }} />
      <m.circle r="38" fill="none" stroke={ACCENT} strokeWidth="1" strokeDasharray="3 6" style={{ opacity: halo }} />
      <m.circle r="9" fill={ACCENT} style={{ opacity: rim }} />
    </g>
  );
};

type ExplodedCoreProps = SVGProps<SVGSVGElement> & { progress: MotionValue<number> };

const ExplodedCore = ({ progress, ...props }: ExplodedCoreProps) => {
  const strongGlow = useTransform(progress, (v) => clamp2((v - 0.4) / 0.5) * 0.6);

  const seam = { half: MID.half - 2, radius: MID.radius - 2, top: MID.top + MID.depth - 1, depth: SEAM_GAP + 1 };

  const inlay = (slab: (typeof PLATE_SLABS)[number]) => (
    <>
      <path d={topPath(slab, 19)} fill="url(#n3-inlay)" stroke="#DDD9D1" strokeWidth="1.2" />
      <path d={topPath(slab, 20.5)} fill="none" stroke="#fff" strokeWidth="1" opacity="0.9" />
    </>
  );

  return (
    <svg viewBox="0 0 1000 1000" aria-hidden {...props}>
      <CoreDefs />

      <Plate index={0} progress={progress}>
        <SlabBody slab={PLATE_SLABS[0]} />
        <SlabTop slab={PLATE_SLABS[0]} groove={10} />
        <PlateNumber slab={PLATE_SLABS[0]} n={1} />
        <FaceMark slab={BASE} side="right" u={0.5} v={0.62} w={4.5} h={4.5} fill="url(#n3-slot)" />
        <FaceMark slab={BASE} side="right" u={0.58} v={0.62} w={4.5} h={4.5} fill="url(#n3-slot)" />
        <FaceMark slab={BASE} side="right" u={0.66} v={0.62} w={4.5} h={4.5} fill="url(#n3-slot)" />
        <FaceMark slab={BASE} side="left" u={0.32} v={0.62} w={4.5} h={4.5} fill="url(#n3-slot)" />
        <FaceMark slab={BASE} side="left" u={0.4} v={0.62} w={4.5} h={4.5} fill="url(#n3-slot)" />
      </Plate>

      <Plate index={1} progress={progress}>
        <SlabBody slab={PLATE_SLABS[1]} />
        <SlabTop slab={PLATE_SLABS[1]} groove={10} />
        <PlateNumber slab={PLATE_SLABS[1]} n={2} />
        <PanelLine slab={BASE} side="left" v={0.3} />
        <PanelLine slab={BASE} side="right" v={0.3} />
      </Plate>

      <Plate index={AI_PLATE} progress={progress}>
        <g className="n3-seam-pulse">
          <path d={topPath(MID, 4, CX, BASE.top - MID.top)} fill={ACCENT} opacity="0.24" filter="url(#n3-blur-spill)" />
          <path d={bodyPath(seam)} fill={ACCENT} opacity="0.6" filter="url(#n3-blur-glow)" />
        </g>
        <m.path d={bodyPath(seam)} fill={ACCENT} filter="url(#n3-blur-glow)" style={{ opacity: strongGlow }} />
        <path d={bodyPath(seam)} fill="url(#n3-seam)" />
        <SlabBody slab={MID} />
        <SlabTop slab={MID} groove={11} />
        <PlateNumber slab={MID} n={3} main />
        <PanelLine slab={MID} side="left" v={0.78} />
        <PanelLine slab={MID} side="right" v={0.78} />
        <FaceMark slab={MID} side="left" u={0.62} v={0.42} w={34} h={7.5} fill="url(#n3-slot)" />
        <FaceMark slab={MID} side="left" u={0.34} v={0.42} w={5} h={5} fill="url(#n3-slot)" />
        <FaceMark slab={MID} side="left" u={0.42} v={0.42} w={5} h={5} fill="url(#n3-slot)" />
        <FaceMark slab={MID} side="right" u={0.44} v={0.42} w={5} h={5} fill="url(#n3-slot)" />
        <FaceMark slab={MID} side="right" u={0.52} v={0.42} w={5} h={5} fill="url(#n3-slot)" />
        <FaceMark slab={MID} side="right" u={0.68} v={0.42} w={22} h={4.5} fill="url(#n3-slot)" />
        <g className="n3-seam-pulse">
          <FaceMark slab={MID} side="left" u={0.2} v={0.42} w={7} h={2.6} fill={ACCENT} glow />
        </g>
        <Fastener slab={MID} x={0} y={-MID.half + 28} />
        <Fastener slab={MID} x={-MID.half + 28} y={0} />
        <Fastener slab={MID} x={MID.half - 28} y={0} />
        <Fastener slab={MID} x={0} y={MID.half - 28} />
        <AiEmphasis progress={progress} />
      </Plate>

      <Plate index={3} progress={progress}>
        <SlabBody slab={PLATE_SLABS[3]} />
        <SlabTop slab={PLATE_SLABS[3]} />
        {inlay(PLATE_SLABS[3])}
        <PlateNumber slab={PLATE_SLABS[3]} n={4} />
      </Plate>

      <Plate index={4} progress={progress}>
        <SlabBody slab={PLATE_SLABS[4]} />
        <SlabTop slab={PLATE_SLABS[4]} />
        {inlay(CAP)}
        <CoreLogo x={CX} y={CAP.top} />
      </Plate>
    </svg>
  );
};

const OrbitalSystem = (props: SVGProps<SVGSVGElement>) => {
  return (
    <svg viewBox="0 0 1000 1000" aria-hidden {...props}>
      <g fill="none" stroke="#D9D6D0" strokeWidth="1">
        <ellipse cx={CX} cy={CY} rx={RING_RX[0]} ry={RING_RX[0] * RING_FLATTEN} opacity="0.8" />
        <ellipse cx={CX} cy={CY} rx={RING_RX[1]} ry={RING_RX[1] * RING_FLATTEN} opacity="0.65" />
      </g>
    </svg>
  );
};

type NodeType = { ring: 0 | 1; angle: number; size: number };

const NODES2: NodeType[] = [
  { ring: 0, angle: 20, size: 7 },
  { ring: 0, angle: 110, size: 5.5 },
  { ring: 0, angle: 200, size: 8 },
  { ring: 0, angle: 290, size: 6 },
  { ring: 1, angle: 60, size: 6 },
  { ring: 1, angle: 132, size: 8 },
  { ring: 1, angle: 204, size: 5.5 },
  { ring: 1, angle: 276, size: 7 },
  { ring: 1, angle: 348, size: 6.5 },
];

const Crystal = ({ size }: { size: number }) => {
  return (
    <g filter="url(#n3-crystal-shadow)">
      <circle r={size * 1.55} fill="url(#n3-crystal-halo)" />
      <circle r={size} fill="url(#n3-crystal-body)" />
      <circle r={size} fill="url(#n3-crystal-refract)" />
      <circle r={size - 0.5} fill="none" stroke="url(#n3-crystal-rim)" strokeWidth="1" />
      <ellipse
        cx={-size * 0.32}
        cy={-size * 0.4}
        rx={size * 0.36}
        ry={size * 0.2}
        transform={`rotate(-30 ${-size * 0.32} ${-size * 0.4})`}
        fill="#FFFFFF"
        opacity="0.95"
      />
      <circle cx={size * 0.34} cy={-size * 0.5} r={Math.max(0.7, size * 0.07)} fill="#FFFFFF" opacity="0.85" />
    </g>
  );
};

type OrbitParticlesProps = SVGProps<SVGSVGElement> & { half: "back" | "front"; animate: boolean; paused?: boolean };

const OrbitParticles = ({ half, animate, paused = false, ...props }: OrbitParticlesProps) => {
  const ref = useRef<SVGSVGElement>(null);

  const clipId = `n3-clip-${half}`;

  useEffect(() => {
    const svg = ref.current;

    if (!svg) return;

    if (paused) svg.pauseAnimations();
    else svg.unpauseAnimations();
  }, [paused]);

  return (
    <svg ref={ref} viewBox="0 0 1000 1000" aria-hidden {...props}>
      <defs>
        <clipPath id={clipId}>
          {half === "back" ? (
            <rect x="-200" y="-200" width="1400" height={CY + 200} />
          ) : (
            <rect x="-200" y={CY} width="1400" height="700" />
          )}
        </clipPath>
        <linearGradient id="n3-crystal-body" x1="0.15" y1="0.1" x2="0.85" y2="0.95">
          <stop offset="0" stopColor="#EDE9FE" stopOpacity="0.9" />
          <stop offset="0.5" stopColor="#A78BFA" stopOpacity="0.88" />
          <stop offset="1" stopColor="#6D28D9" stopOpacity="0.95" />
        </linearGradient>
        <radialGradient id="n3-crystal-refract" cx="0.6" cy="0.78" r="0.45">
          <stop offset="0" stopColor="#F5F3FF" stopOpacity="0.85" />
          <stop offset="1" stopColor="#F5F3FF" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="n3-crystal-rim" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.95" />
          <stop offset="1" stopColor="#6D28D9" stopOpacity="0.55" />
        </linearGradient>
        <radialGradient id="n3-crystal-halo" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0.5" stopColor={ACCENT} stopOpacity="0.12" />
          <stop offset="1" stopColor={ACCENT} stopOpacity="0" />
        </radialGradient>
        <filter id="n3-crystal-shadow" x="-80%" y="-80%" width="260%" height="260%">
          <feDropShadow dx="0" dy="2.5" stdDeviation="2.5" floodColor="#4C1D95" floodOpacity="0.25" />
        </filter>
      </defs>

      <g clipPath={`url(#${clipId})`}>
        {NODES2.map((node, i) => {
          const rx = RING_RX[node.ring];
          const [x, y] = ringPoint(rx, node.angle);
          const dur = MOTION.orbitSeconds[node.ring];
          const reverse = node.ring === 1;

          const start = node.angle / 360;
          const begin = -dur * (reverse ? 1 - start : start);

          return (
            <g key={i} transform={animate ? undefined : `translate(${x.toFixed(1)} ${y.toFixed(1)})`}>
              <Crystal size={node.size} />
              {animate && (
                <animateMotion
                  dur={`${dur}s`}
                  begin={`${begin}s`}
                  repeatCount="indefinite"
                  path={ringPath(rx)}
                  {...(reverse && { keyPoints: "1;0", keyTimes: "0;1", calcMode: "linear" })}
                />
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
};

const DOTS = Array.from({ length: 26 }, (_, i) => {
  const a = (i * 137.5 * Math.PI) / 180;
  const r = 160 + ((i * 53) % 340);

  return [
    round(CX + r * Math.cos(a) * 1.02),
    round(CY + r * Math.sin(a) * RING_FLATTEN * 1.6),
    0.8 + (i % 3) * 0.5,
  ] as const;
});

const TechnicalBackdrop = (props: SVGProps<SVGSVGElement>) => {
  return (
    <svg viewBox="0 0 1000 1000" aria-hidden {...props}>
      <defs>
        <linearGradient id="n3-axis-v" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#C9C5BC" stopOpacity="0" />
          <stop offset="0.5" stopColor="#C9C5BC" stopOpacity="0.45" />
          <stop offset="1" stopColor="#C9C5BC" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="n3-axis-h" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#C9C5BC" stopOpacity="0" />
          <stop offset="0.5" stopColor="#C9C5BC" stopOpacity="0.7" />
          <stop offset="1" stopColor="#C9C5BC" stopOpacity="0" />
        </linearGradient>
      </defs>

      <rect x={CX - 0.5} y="110" width="1" height="780" fill="url(#n3-axis-v)" />
      <rect x="70" y={CY - 0.5} width="860" height="1" fill="url(#n3-axis-h)" />

      <g fill="#C9C5BC">
        {DOTS.map(([x, y, r], i) => (
          <circle key={i} cx={x} cy={y} r={r} opacity={0.35 + (i % 4) * 0.12} />
        ))}
      </g>

      <g stroke="#C9C5BC" strokeWidth="1" opacity="0.5">
        {(
          [
            [212, 292],
            [790, 690],
            [860, 430],
            [150, 560],
          ] as const
        ).map(([x, y]) => (
          <path key={`${x}-${y}`} d={`M${x - 5} ${y}h10M${x} ${y - 5}v10`} />
        ))}
      </g>
    </svg>
  );
};

// ───── logos: only the integrations Fixify actually has (docs/github-oauth.md, docs/ai.md) ─────

const GithubLogo = (props: SVGProps<SVGSVGElement>) => {
  return (
    <svg viewBox="0 0 256 250" aria-hidden {...props}>
      <path
        fill="#161614"
        d="M128.001 0C57.317 0 0 57.307 0 128.001c0 56.554 36.676 104.535 87.535 121.46c6.397 1.185 8.746-2.777 8.746-6.158c0-3.052-.12-13.135-.174-23.83c-35.61 7.742-43.124-15.103-43.124-15.103c-5.823-14.795-14.213-18.73-14.213-18.73c-11.613-7.944.876-7.78.876-7.78c12.853.902 19.621 13.19 19.621 13.19c11.417 19.568 29.945 13.911 37.249 10.64c1.149-8.272 4.466-13.92 8.127-17.116c-28.431-3.236-58.318-14.212-58.318-63.258c0-13.975 5-25.394 13.188-34.358c-1.329-3.224-5.71-16.242 1.24-33.874c0 0 10.749-3.44 35.21 13.121c10.21-2.836 21.16-4.258 32.038-4.307c10.878.049 21.837 1.47 32.066 4.307c24.431-16.56 35.165-13.12 35.165-13.12c6.967 17.63 2.584 30.65 1.255 33.873c8.207 8.964 13.173 20.383 13.173 34.358c0 49.163-29.944 59.988-58.447 63.157c4.591 3.972 8.682 11.762 8.682 23.704c0 17.126-.148 30.91-.148 35.126c0 3.407 2.304 7.398 8.792 6.14C219.37 232.5 256 184.537 256 128.002C256 57.307 198.691 0 128.001 0"
      />
    </svg>
  );
};

const GeminiLogo = (props: SVGProps<SVGSVGElement>) => {
  return (
    <svg viewBox="0 0 16 16" aria-hidden {...props}>
      <path
        fill="#448aff"
        d="M15 8.014A7.457 7.457 0 0 0 8.014 15h-.028A7.456 7.456 0 0 0 1 8.014v-.028A7.456 7.456 0 0 0 7.986 1h.028A7.457 7.457 0 0 0 15 7.986z"
      />
    </svg>
  );
};

const ClaudeLogo = (props: SVGProps<SVGSVGElement>) => {
  return (
    <svg viewBox="0 0 256 257" aria-hidden {...props}>
      <path
        fill="#d97757"
        d="m50.228 170.321l50.357-28.257l.843-2.463l-.843-1.361h-2.462l-8.426-.518l-28.775-.778l-24.952-1.037l-24.175-1.296l-6.092-1.297L0 125.796l.583-3.759l5.12-3.434l7.324.648l16.202 1.101l24.304 1.685l17.629 1.037l26.118 2.722h4.148l.583-1.685l-1.426-1.037l-1.101-1.037l-25.147-17.045l-27.22-18.017l-14.258-10.37l-7.713-5.25l-3.888-4.925l-1.685-10.758l7-7.713l9.397.649l2.398.648l9.527 7.323l20.35 15.75L94.817 91.9l3.889 3.24l1.555-1.102l.195-.777l-1.75-2.917l-14.453-26.118l-15.425-26.572l-6.87-11.018l-1.814-6.61c-.648-2.723-1.102-4.991-1.102-7.778l7.972-10.823L71.42 0l10.63 1.426l4.472 3.888l6.61 15.101l10.694 23.786l16.591 32.34l4.861 9.592l2.592 8.879l.973 2.722h1.685v-1.556l1.36-18.211l2.528-22.36l2.463-28.776l.843-8.1l4.018-9.722l7.971-5.25l6.222 2.981l5.12 7.324l-.713 4.73l-3.046 19.768l-5.962 30.98l-3.889 20.739h2.268l2.593-2.593l10.499-13.934l17.628-22.036l7.778-8.749l9.073-9.657l5.833-4.601h11.018l8.1 12.055l-3.628 12.443l-11.342 14.388l-9.398 12.184l-13.48 18.147l-8.426 14.518l.778 1.166l2.01-.194l30.46-6.481l16.462-2.982l19.637-3.37l8.88 4.148l.971 4.213l-3.5 8.62l-20.998 5.184l-24.628 4.926l-36.682 8.685l-.454.324l.519.648l16.526 1.555l7.065.389h17.304l32.21 2.398l8.426 5.574l5.055 6.805l-.843 5.184l-12.962 6.611l-17.498-4.148l-40.83-9.721l-14-3.5h-1.944v1.167l11.666 11.406l21.387 19.314l26.767 24.887l1.36 6.157l-3.434 4.86l-3.63-.518l-23.526-17.693l-9.073-7.972l-20.545-17.304h-1.36v1.814l4.73 6.935l25.017 37.59l1.296 11.536l-1.814 3.76l-6.481 2.268l-7.13-1.297l-14.647-20.544l-15.1-23.138l-12.185-20.739l-1.49.843l-7.194 77.448l-3.37 3.953l-7.778 2.981l-6.48-4.925l-3.436-7.972l3.435-15.749l4.148-20.544l3.37-16.333l3.046-20.285l1.815-6.74l-.13-.454l-1.49.194l-15.295 20.999l-23.267 31.433l-18.406 19.702l-4.407 1.75l-7.648-3.954l.713-7.064l4.277-6.286l25.47-32.405l15.36-20.092l9.917-11.6l-.065-1.686h-.583L44.07 198.125l-12.055 1.555l-5.185-4.86l.648-7.972l2.463-2.593l20.35-13.999z"
      />
    </svg>
  );
};

type AppName = Stage["apps"][number];

const APP_LOGOS: Record<AppName, (props: SVGProps<SVGSVGElement>) => ReactElement> = {
  GitHub: GithubLogo,
  Gemini: GeminiLogo,
  Claude: ClaudeLogo,
};

const STAGE_ICONS = {
  sources: Cable,
  context: FilePen,
  review: UserCheck,
  outcomes: GitPullRequest,
};

type AppLogosProps = { stage: Stage; tiles: boolean; className?: string };

const AppLogos = ({ stage, tiles, className }: AppLogosProps) => {
  if (stage.apps.length === 0) return null;

  return (
    <div className={cn("n3-stage-apps flex shrink-0 items-center", tiles ? "gap-[0.45em]" : "gap-[0.3em]", className)}>
      {stage.apps.map((app) => {
        const Logo = APP_LOGOS[app];

        return tiles ? (
          <span
            key={app}
            className="border-(color:--color-n3-line) grid size-[2.15em] place-items-center rounded-[0.6em] border bg-white shadow-[0_1px_2px_rgb(60_50_40/0.06)]"
          >
            <Logo className="size-[1.2em]" />
          </span>
        ) : (
          <Logo key={app} className="size-[1.45em]" />
        );
      })}
      <span className="sr-only">Works with {stage.apps.join(", ")}</span>
    </div>
  );
};

const StageCardBody = ({ index }: { index: number }) => {
  const stage = STAGES[index];
  const main = isMain(stage);
  const Icon = "icon" in stage ? STAGE_ICONS[stage.icon] : null;

  return (
    <div className="grid grid-cols-[1.35em_minmax(0,1fr)_auto] items-start gap-x-[0.5em]">
      <span className="text-(color:--color-n3-grey) col-start-1 row-start-1 flex h-[1.64em] items-center text-[0.8em] font-medium tabular-nums">
        {String(index + 1).padStart(2, "0")}
      </span>
      <div
        className={cn(
          "col-start-2 row-start-1 flex flex-wrap items-baseline justify-between gap-x-[0.6em]",
          main && "col-span-2"
        )}
      >
        <p className="text-(color:--color-n3-ink) text-[1.05em] leading-[1.25] font-semibold tracking-[-0.015em] md:whitespace-nowrap">
          {stage.title}
        </p>
        {main && (
          <span className="text-(color:--color-n3-accent) shrink-0 text-[0.72em] font-semibold tracking-[0.12em] uppercase">
            Main layer
          </span>
        )}
      </div>

      {Icon && (
        <span className="col-start-1 row-start-2 mt-[0.4em] flex h-[1.276em] items-center">
          <Icon className="text-(color:--color-n3-accent) size-[1.25em]" strokeWidth={1.7} aria-hidden />
        </span>
      )}
      <div className={cn("col-start-2 row-start-2 mt-[0.4em]", main && "col-span-2")}>
        <p className="text-(color:--color-n3-grey) text-[0.88em] leading-[1.45]">{stage.items.join(" · ")}</p>
        {main && <AppLogos stage={stage} tiles className="mt-[0.75em] justify-end" />}
      </div>

      {!main && <AppLogos stage={stage} tiles={false} className="col-start-3 row-span-2 row-start-1 self-center" />}
    </div>
  );
};

const pct = (n: number) => `${(n / ARTBOARD) * 100}%`;

const cardDirection = (index: number) => (STAGES[index].side === "left" ? -1 : 1);

type StageCardProps = {
  index: number;
  progress: MotionValue<number>;
  open: boolean;
  lit: boolean;
  onHover: (index: number | null) => void;
};

const StageCard = ({ index, progress, open, lit, onHover }: StageCardProps) => {
  const opacity = useTransform(progress, [0.35, 0.9], [0, 1]);

  const x = useTransform(
    progress,
    [0, 1],
    [-cardDirection(index) * STAGE_CARDS.restInset, cardDirection(index) * STAGE_CARDS.outward]
  );

  const stage = STAGES[index];
  const { edge, width } = STAGE_CARDS[stage.side];
  const left = stage.side === "left" ? edge : 100 - edge - width;

  const handlePointerEnter = (e: ReactPointerEvent) => {
    if (e.pointerType === "mouse") onHover(index);
  };

  const handlePointerLeave = () => {
    onHover(null);
  };

  return (
    <li
      style={{ top: pct(cornerY(index)), left: `${left}%`, width: `${width}%` }}
      className="absolute -translate-y-1/2"
    >
      <m.div
        style={{ opacity, x }}
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
        className={cn(
          "n3-stage-card px-[0.9em] py-[0.85em]",
          open && "pointer-events-auto",
          lit && "n3-stage-card-lit"
        )}
      >
        <StageCardBody index={index} />
      </m.div>
    </li>
  );
};

type StageCardsProps = {
  progress: MotionValue<number>;
  open: boolean;
  hovered: number | null;
  onHover: (index: number | null) => void;
};

const StageCards = ({ progress, open, hovered, onHover }: StageCardsProps) => {
  return (
    <ul
      aria-label="How Fixify works"
      aria-hidden={!open}
      className="pointer-events-none absolute inset-0 m-0 hidden list-none p-0 text-[clamp(10px,1.7cqw,15px)] md:block"
    >
      {STAGES.map((stage, i) => (
        <StageCard key={stage.title} index={i} progress={progress} open={open} lit={hovered === i} onHover={onHover} />
      ))}
    </ul>
  );
};

type StageConnectorProps = {
  className?: string;
  plate: number;
  card: number;
  y: number;
  side: "left" | "right";
  index: number;
  main: boolean;
  lit: boolean;
  active: boolean;
  progress: MotionValue<number>;
};

const lineEnds = (plate: number, card: number, side: "left" | "right") => {
  const dir = side === "right" ? 1 : -1;

  return { plateX: plate + dir * 7, nodeX: card - dir * 10 };
};

const StageConnector = ({
  plate,
  card,
  y,
  side,
  index,
  main,
  lit,
  active,
  progress,
  className,
}: StageConnectorProps) => {
  const show = useTransform(progress, [0.55, 0.9], [0, 1]);
  const t = useMotionValue(0);

  const beadX = useTransform(t, (k) => {
    const ends = lineEnds(plate, card, side);

    return ends.nodeX + (ends.plateX - ends.nodeX) * k;
  });

  const beadOpacity = useTransform([t, show], ([k, s]: number[]) => s * Math.sin(Math.PI * k));

  const { plateX, nodeX } = lineEnds(plate, card, side);

  useEffect(() => {
    if (!active) return;

    const controls = animate(t, [0, 1], {
      duration: STAGE_CARDS.beadSeconds,
      ease: "easeInOut",
      repeat: Infinity,
      repeatDelay: 1.4,
      delay: 0.5 + index * 0.25,
    });

    return () => {
      controls.stop();
      t.set(0);
    };
  }, [active, index, t]);

  return (
    <m.svg aria-hidden viewBox={`0 0 ${ARTBOARD} ${ARTBOARD}`} style={{ opacity: show }} className={className}>
      <line x1={plateX} x2={nodeX} y1={y} y2={y} stroke="#CFCAC1" strokeWidth="1" />
      <m.line
        x1={plateX}
        x2={nodeX}
        y1={y}
        y2={y}
        stroke={ACCENT}
        strokeWidth="1.2"
        initial={false}
        animate={{ opacity: lit ? 0.9 : 0 }}
        transition={{ duration: 0.25 }}
      />
      <circle cx={plateX} cy={y} r="2.6" fill="#A8A399" />
      <m.circle
        cx={nodeX}
        cy={y}
        r={main ? 10 : 8}
        fill={ACCENT}
        initial={false}
        animate={{ opacity: lit || main ? 0.22 : 0.12 }}
        transition={{ duration: 0.25 }}
      />
      <circle cx={nodeX} cy={y} r="3.6" fill={ACCENT} />
      <m.circle cx={beadX} cy={y} r="2.6" fill={ACCENT} style={{ opacity: beadOpacity }} />
    </m.svg>
  );
};

type StageConnectorsProps = {
  progress: MotionValue<number>;
  active: boolean;
  hovered: number | null;
};

const StageConnectors = ({ progress, active, hovered }: StageConnectorsProps) => {
  return (
    <div className="pointer-events-none absolute inset-0 hidden md:block">
      {STAGES.map((stage, i) => {
        const { edge, width } = STAGE_CARDS[stage.side];
        const cardEdge = stage.side === "left" ? (edge + width) * 10 : (100 - edge - width) * 10;

        return (
          <StageConnector
            key={stage.title}
            plate={tipX(i, stage.side)}
            card={cardEdge}
            y={cornerY(i)}
            side={stage.side}
            index={i}
            main={isMain(stage)}
            lit={hovered === i}
            active={active}
            progress={progress}
            className="pointer-events-none absolute inset-0 size-full overflow-visible"
          />
        );
      })}
    </div>
  );
};

const StageList = ({ reduce }: { reduce: boolean }) => {
  return (
    <m.ul
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.9, delay: 0.5, ease: EASE }}
      aria-label="How Fixify works"
      className="m-0 grid list-none grid-cols-1 gap-2.5 p-0 text-[13px] sm:grid-cols-2 md:hidden"
    >
      {STAGES.map((stage, i) => (
        <li key={stage.title} className="n3-stage-card px-[1.05em] py-[0.95em]">
          <StageCardBody index={i} />
        </li>
      ))}
    </m.ul>
  );
};

const subscribeToVisibility = (onChange: () => void) => {
  document.addEventListener("visibilitychange", onChange);

  return () => document.removeEventListener("visibilitychange", onChange);
};

const isPageVisible = () => !document.hidden;
const isPageVisibleOnServer = () => true;

type ParallaxLayerProps = {
  x: MotionValue<number>;
  y: MotionValue<number>;
  reach: number;
  children: ReactNode;
};

const ParallaxLayer = ({ x, y, reach, children }: ParallaxLayerProps) => {
  const tx = useTransform(x, (v) => v * reach);
  const ty = useTransform(y, (v) => v * reach);

  return (
    <m.div style={{ x: tx, y: ty }} className="pointer-events-none absolute inset-0">
      {children}
    </m.div>
  );
};

type TiltedProps = {
  rotateX: MotionValue<number>;
  rotateY: MotionValue<number>;
  children: ReactNode;
};

const Tilted = ({ rotateX, rotateY, children }: TiltedProps) => {
  return (
    <div className="pointer-events-none absolute inset-0 [perspective:1400px]">
      <m.div style={{ rotateX, rotateY }} className="absolute inset-0">
        <div className="n3-float absolute inset-0">{children}</div>
      </m.div>
    </div>
  );
};

const CoreVisual = () => {
  const [open, setOpen] = useState(false);
  const [hovered, setHovered] = useState<number | null>(null);

  const pointerType = useRef("mouse");
  const visualRef = useRef<HTMLDivElement>(null);

  const reduce = useReducedMotion() ?? false;

  const onScreen = useInView(visualRef, { initial: true, margin: "40px" });
  const pageVisible = useSyncExternalStore(subscribeToVisibility, isPageVisible, isPageVisibleOnServer);

  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const x = useSpring(px, { stiffness: 55, damping: 18, mass: 0.9 });
  const y = useSpring(py, { stiffness: 55, damping: 18, mass: 0.9 });
  const rotateY = useTransform(x, (v) => v * MOTION.tiltDegrees);

  const target = useMotionValue(0);
  const progress = useSpring(target, reduce ? { duration: 0.01 } : EXPLODE.spring);

  const rotateX = useTransform([y, progress], ([v, p]: number[]) => v * -MOTION.tiltDegrees + p * 4);
  const restOpacity = useTransform(progress, [0, 0.04], [1, 0]);
  const explodedOpacity = useTransform(progress, [0, 0.03], [0, 1]);
  const shadowOpacity = useTransform(progress, [0, 1], [1, 0.55]);

  const orbitOpacity = useTransform(progress, [0, 0.6], [1, MOTION.orbitOpenOpacity]);

  const hintOpacity = useTransform(progress, [0, 0.25], [1, 0]);

  const beadsPaused = open || !onScreen || !pageVisible;

  useEffect(() => {
    target.set(open ? 1 : 0);
  }, [open, target]);

  const handlePointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (reduce || e.pointerType !== "mouse") return;

    const box = e.currentTarget.getBoundingClientRect();

    px.set(((e.clientX - box.left) / box.width - 0.5) * 2);
    py.set(((e.clientY - box.top) / box.height - 0.5) * 2);
  };

  const handlePointerLeave = () => {
    px.set(0);
    py.set(0);
    setOpen(false);
  };

  const handleCardHover = (index: number | null) => {
    setHovered(index);
    if (index !== null && !reduce) setOpen(true);
  };

  const handleCorePointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
    pointerType.current = e.pointerType;
  };

  const handleCorePointerEnter = (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (e.pointerType === "mouse" && !reduce) setOpen(true);
  };

  const handleCoreClick = (e: MouseEvent<HTMLButtonElement>) => {
    if (e.detail === 0 || pointerType.current !== "mouse") setOpen((v) => !v);
  };

  const handleCoreBlur = () => {
    setOpen(false);
  };

  return (
    <LazyMotion features={domAnimation}>
      <>
        <div
          ref={visualRef}
          onPointerMove={handlePointerMove}
          onPointerLeave={handlePointerLeave}
          className="n3-enter @container relative -my-[6%] -ml-[12.5%] aspect-square w-[125%] max-w-none md:mx-auto md:my-0 md:w-full md:max-w-[840px] lg:mx-0 lg:w-[104%] lg:max-w-none"
        >
          <div className="absolute inset-0">
            <div aria-hidden className="n3-halo pointer-events-none absolute inset-[6%]" />

            <div className="n3-fade-edge absolute inset-0">
              <ParallaxLayer x={x} y={y} reach={-MOTION.backdropParallax}>
                <DepthBackdrop className="absolute inset-0 size-full overflow-visible" />
                <TechnicalBackdrop className="absolute inset-0 size-full overflow-visible" />
              </ParallaxLayer>
            </div>

            <ParallaxLayer x={x} y={y} reach={MOTION.ringParallax}>
              <m.div style={{ opacity: orbitOpacity }} className="absolute inset-0">
                <OrbitalSystem className="absolute inset-0 size-full overflow-visible" />
                <OrbitParticles
                  half="back"
                  animate={!reduce}
                  paused={beadsPaused}
                  className="absolute inset-0 size-full overflow-visible"
                />
              </m.div>
            </ParallaxLayer>

            <m.div style={{ opacity: shadowOpacity }} className="absolute inset-0">
              <CoreShadow className="pointer-events-none absolute inset-0 size-full overflow-visible" />
            </m.div>

            <Tilted rotateX={rotateX} rotateY={rotateY}>
              <m.div style={{ opacity: restOpacity }} className="absolute inset-0">
                <CoreObject className="absolute inset-0 size-full overflow-visible" />
              </m.div>
              <m.div style={{ opacity: explodedOpacity }} className="absolute inset-0">
                <ExplodedCore progress={progress} className="absolute inset-0 size-full overflow-visible" />
              </m.div>
              <StageConnectors progress={progress} active={open && !reduce} hovered={hovered} />
            </Tilted>

            <ParallaxLayer x={x} y={y} reach={MOTION.ringParallax}>
              <m.div style={{ opacity: orbitOpacity }} className="absolute inset-0">
                <OrbitParticles
                  half="front"
                  animate={!reduce}
                  paused={beadsPaused}
                  className="absolute inset-0 size-full overflow-visible"
                />
              </m.div>
            </ParallaxLayer>

            <Tilted rotateX={rotateX} rotateY={rotateY}>
              <StageCards progress={progress} open={open} hovered={hovered} onHover={handleCardHover} />
            </Tilted>
          </div>

          <m.p
            aria-hidden
            style={{ opacity: hintOpacity }}
            className="text-(color:--color-n3-grey) pointer-events-none absolute top-[84%] left-1/2 m-0 flex -translate-x-1/2 items-center gap-1.5 text-[12.5px] whitespace-nowrap"
          >
            <MousePointer2 className="text-(color:--color-n3-accent) size-3.5" strokeWidth={1.8} />
            <span className="[@media(hover:none)]:hidden">Hover to see how it works</span>
            <span className="hidden [@media(hover:none)]:inline">Tap to see how it works</span>
          </m.p>

          <button
            type="button"
            aria-expanded={open}
            aria-label="Show how Fixify works inside"
            onPointerDown={handleCorePointerDown}
            onPointerEnter={handleCorePointerEnter}
            onClick={handleCoreClick}
            onBlur={handleCoreBlur}
            className="focus-visible:outline-(color:--color-n3-accent) absolute top-[30%] left-[22%] h-[44%] w-[56%] cursor-default rounded-[3rem] focus-visible:outline-2 focus-visible:outline-offset-4"
          />
        </div>
        <StageList reduce={reduce} />
      </>
    </LazyMotion>
  );
};

const FlipLabel = ({ children, className }: { children: ReactNode; className?: string }) => {
  return (
    <span className="n3-flip-box">
      <span className={cn("n3-flip-face", className)}>{children}</span>
      <span aria-hidden className={cn("n3-flip-face n3-flip-back", className)}>
        {children}
      </span>
    </span>
  );
};

const rise = (delay: number) => ({ style: { animationDelay: `${delay}s` } });

const HeroCopy = () => {
  return (
    <div className="flex flex-col justify-center">
      <h1 id="n3-title" {...rise(0.1)} className="n3-rise n3-h1 text-(color:--color-n3-ink) font-normal">
        {COPY.headline.map((line) => (
          <span
            key={line}
            className={cn("block", line === COPY.accentLine && "text-(color:--color-n3-accent) italic")}
          >
            {line}
          </span>
        ))}
      </h1>

      <p {...rise(0.3)} className="n3-rise text-(color:--color-n3-grey) mt-7 max-w-[30rem] text-[17px] leading-[1.6] lg:text-[19px]">
        {COPY.body}
      </p>

      <div {...rise(0.4)} className="n3-rise mt-9 flex flex-wrap items-center gap-3">
        <Link
          href={COPY.primaryCtaHref}
          className="n3-flip bg-(color:--color-n3-accent) focus-visible:outline-(color:--color-n3-ink) inline-flex h-13 items-center rounded-full px-7 text-[16px] font-medium text-white focus-visible:outline-2 focus-visible:outline-offset-2 sm:h-14"
        >
          <FlipLabel className="gap-2.5">
            {COPY.primaryCta}
            <ArrowRight className="size-4" strokeWidth={1.8} aria-hidden />
          </FlipLabel>
        </Link>
        <a
          href={COPY.secondaryCtaHref}
          className="n3-flip border-(color:--color-n3-line) text-(color:--color-n3-ink) focus-visible:outline-(color:--color-n3-accent) inline-flex h-13 items-center rounded-full border bg-white/50 px-6 text-[16px] focus-visible:outline-2 focus-visible:outline-offset-2 sm:h-14"
        >
          <FlipLabel className="gap-3">
            <span className="border-(color:--color-n3-ink) grid size-5 place-items-center rounded-full border">
              <ArrowRight className="size-2.5" strokeWidth={2} aria-hidden />
            </span>
            {COPY.secondaryCta}
          </FlipLabel>
        </a>
      </div>

      <dl {...rise(0.58)} className="n3-rise mt-12 grid grid-cols-3 sm:flex sm:items-stretch lg:mt-20">
        {METRICS.map(({ value, label, icon }, i) => {
          const Icon = ICONS[icon];

          return (
            <div
              key={label}
              className={cn(
                "flex flex-col items-start gap-2 pr-3 sm:flex-row sm:items-center sm:gap-3 sm:pr-8",
                i > 0 && "border-(color:--color-n3-line) border-l pl-4 sm:pl-8"
              )}
            >
              <Icon className="text-(color:--color-n3-ink) size-8 shrink-0" strokeWidth={1.25} aria-hidden />
              <div>
                <dd className="text-(color:--color-n3-ink) text-[14px] leading-5 font-medium">{value}</dd>
                <dt className="text-(color:--color-n3-grey) text-[13px] leading-5">{label}</dt>
              </div>
            </div>
          );
        })}
      </dl>
    </div>
  );
};

const CELL = { w: 84, h: 48 };

type FloorGridProps = SVGProps<SVGSVGElement> & { id: string; stroke?: string; strokeWidth?: number };

const FloorGrid = ({ id, stroke = "#D3CFC6", strokeWidth = 0.8, ...props }: FloorGridProps) => {
  return (
    <svg aria-hidden width="100%" height="100%" {...props}>
      <defs>
        <pattern id={id} width={CELL.w} height={CELL.h} patternUnits="userSpaceOnUse">
          <path
            d={`M0 ${CELL.h / 2}L${CELL.w / 2} 0L${CELL.w} ${CELL.h / 2}M0 ${CELL.h / 2}L${CELL.w / 2} ${CELL.h}L${CELL.w} ${CELL.h / 2}`}
            fill="none"
            stroke={stroke}
            strokeWidth={strokeWidth}
          />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  );
};

const SPOT = 340;

const HeroFloor = () => {
  const ref = useRef<HTMLDivElement>(null);
  const spotRef = useRef<HTMLDivElement>(null);
  const litRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    const spot = spotRef.current;
    const lit = litRef.current;
    const section = el?.parentElement;

    if (!el || !spot || !lit || !section) return;

    const resize = new ResizeObserver(([entry]) => {
      lit.style.width = `${entry.contentRect.width}px`;
      lit.style.height = `${entry.contentRect.height}px`;
    });

    resize.observe(section);

    let frame = 0;

    const handlePointerMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse") return;

      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const box = section.getBoundingClientRect();
        const x = e.clientX - box.left - SPOT / 2;
        const y = e.clientY - box.top - SPOT / 2;

        spot.style.transform = `translate3d(${x}px, ${y}px, 0)`;
        lit.style.transform = `translate3d(${-x}px, ${-y}px, 0)`;
        el.dataset.spot = "on";
      });
    };

    const handlePointerLeave = () => {
      cancelAnimationFrame(frame);
      el.dataset.spot = "off";
    };

    section.addEventListener("pointermove", handlePointerMove);
    section.addEventListener("pointerleave", handlePointerLeave);

    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      section.removeEventListener("pointermove", handlePointerMove);
      section.removeEventListener("pointerleave", handlePointerLeave);
    };
  }, []);

  return (
    <div ref={ref} aria-hidden data-spot="off" className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <FloorGrid id="n3-floor-cell" className="n3-floor absolute inset-0" />
      <div ref={spotRef} style={{ width: SPOT, height: SPOT }} className="n3-floor-spot">
        <div ref={litRef} className="n3-floor-lit">
          <FloorGrid id="n3-floor-cell-lit" stroke="#7C3AED" strokeWidth={1} className="block size-full" />
        </div>
      </div>
    </div>
  );
};

const Hero = () => {
  return (
    <section id="top" aria-labelledby="n3-title" className="n3-hero relative isolate overflow-x-clip">
      <HeroFloor />
      <div className="n3-frame mx-auto grid max-w-360 items-center gap-6 pt-6 pb-12 lg:min-h-[inherit] lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-12 lg:py-10 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] xl:gap-20">
        <HeroCopy />
        <CoreVisual />
      </div>
    </section>
  );
};

const Navbar = () => {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  const wrapRef = useRef<HTMLDivElement>(null);

  const reduce = useReducedMotion();

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 12);

    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });

    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    const el = wrapRef.current;
    const root = el?.closest<HTMLElement>(".n3-root");

    if (!el || !root) return;

    const measure = () => root.style.setProperty("--n3-nav-space", `${el.getBoundingClientRect().height}px`);
    const observer = new ResizeObserver(measure);

    measure();
    observer.observe(el);
    document.fonts?.ready.then(measure);

    return () => observer.disconnect();
  }, []);

  const handleMenuToggle = () => {
    setOpen((v) => !v);
  };

  const handleMenuClose = () => {
    setOpen(false);
  };

  const mobileLinks = [...NAV_LINKS, { label: "Sign in", href: "/login" }];

  return (
    <LazyMotion features={domAnimation}>
      <header ref={wrapRef} className="n3-drop sticky top-0 z-50">
        <div className={cn("n3-nav-bar", (scrolled || open) && "n3-nav-bar-scrolled")}>
          <nav
            aria-label="Primary"
            className="n3-frame mx-auto flex h-18 max-w-360 items-center justify-between lg:h-24"
          >
            <Link href="/" aria-label="Fixify home" className="text-(color:--color-n3-ink) flex items-center gap-2.5">
              <LogoMark className="size-9" />
              <span className="text-[26px] font-medium tracking-[-0.04em]">Fixify</span>
            </Link>

            <ul className="hidden items-center gap-10 lg:flex">
              {NAV_LINKS.map(({ label, href }) => (
                <li key={label}>
                  <a
                    href={href}
                    className="text-(color:--color-n3-ink) hover:text-(color:--color-n3-accent) focus-visible:text-(color:--color-n3-accent) inline-flex items-center py-2 text-[16px] transition-colors duration-200 focus-visible:outline-none"
                  >
                    {label}
                  </a>
                </li>
              ))}
            </ul>

            <div className="flex items-center gap-2 sm:gap-4">
              <ThemeToggle />
              <Link
                href="/login"
                className="text-(color:--color-n3-ink) hover:text-(color:--color-n3-accent) hidden px-3 py-2 text-[16px] transition-colors duration-200 sm:block"
              >
                Sign in
              </Link>
              <Link
                href={COPY.primaryCtaHref}
                className="n3-flip bg-(color:--color-n3-ink) focus-visible:outline-(color:--color-n3-accent) inline-flex h-11 items-center rounded-full px-5 text-[15px] font-medium text-white focus-visible:outline-2 focus-visible:outline-offset-2 sm:h-13 sm:px-6 sm:text-[16px]"
              >
                <FlipLabel className="gap-2">
                  {COPY.primaryCta}
                  <ArrowRight className="size-4" strokeWidth={1.8} aria-hidden />
                </FlipLabel>
              </Link>
              <button
                type="button"
                aria-label={open ? "Close menu" : "Open menu"}
                aria-expanded={open}
                aria-controls="n3-mobile-menu"
                onClick={handleMenuToggle}
                className="text-(color:--color-n3-ink) grid size-11 place-items-center rounded-full lg:hidden"
              >
                {open ? <X className="size-5" strokeWidth={1.6} /> : <Menu className="size-5" strokeWidth={1.6} />}
              </button>
            </div>
          </nav>

          <AnimatePresence initial={false}>
            {open && (
              <m.div
                id="n3-mobile-menu"
                initial={reduce ? false : { opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
                transition={{ duration: 0.22, ease: EASE }}
                className="n3-frame pb-5 lg:hidden"
              >
                <ul className="border-(color:--color-n3-ink)/8 flex flex-col border-t pt-2">
                  {mobileLinks.map(({ label, href }) => (
                    <li key={label}>
                      <a href={href} onClick={handleMenuClose} className="text-(color:--color-n3-ink) flex h-12 items-center text-[16px]">
                        {label}
                      </a>
                    </li>
                  ))}
                </ul>
              </m.div>
            )}
          </AnimatePresence>
        </div>
      </header>
    </LazyMotion>
  );
};

const motionVars = {
  "--n3-float": MOTION.floatDistance,
  "--n3-float-seconds": `${MOTION.floatSeconds}s`,
} as CSSProperties;

export default function CoreHero() {
  return (
    <>
      <style>{BLOCK_CSS}</style>
      <div
        style={motionVars}
        className="n3-root n3-bg font-(family-name:--font-n3-sans) text-(color:--color-n3-ink) w-full antialiased"
      >
        <Navbar />
        <Hero />
      </div>
    </>
  );
}
