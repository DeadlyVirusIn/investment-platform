// Phase 4 — minimal inline SVG icon set.
// No external library (lucide-react not installed). Stroke-based icons
// inherit currentColor; size props are explicit for layout stability.
//
// Replaces Unicode glyphs ◇ ▸ ✓ ✕ ⚠ ◯ used as UI controls/status marks.

import type { SVGProps } from "react";


export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "ref"> {
  size?: number;
  strokeWidth?: number;
}


function base(p: IconProps) {
  const { size = 14, strokeWidth = 1.75, ...rest } = p;
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    ...rest,
  };
}


export function ChevronRight(p: IconProps) {
  return <svg {...base(p)}><polyline points="9 18 15 12 9 6" /></svg>;
}

export function ChevronDown(p: IconProps) {
  return <svg {...base(p)}><polyline points="6 9 12 15 18 9" /></svg>;
}

export function Check(p: IconProps) {
  return <svg {...base(p)}><polyline points="20 6 9 17 4 12" /></svg>;
}

export function X(p: IconProps) {
  return (
    <svg {...base(p)}>
      <line x1="18" y1="6"  x2="6"  y2="18" />
      <line x1="6"  y1="6"  x2="18" y2="18" />
    </svg>
  );
}

export function AlertTriangle(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9"  x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

export function Clock(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

export function Circle(p: IconProps) {
  return <svg {...base(p)}><circle cx="12" cy="12" r="10" /></svg>;
}

export function Activity(p: IconProps) {
  return (
    <svg {...base(p)}>
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

export function Info(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8"  x2="12.01" y2="8" />
    </svg>
  );
}

export function Diamond(p: IconProps) {
  return (
    <svg {...base(p)}>
      <polygon points="12 2 22 12 12 22 2 12 12 2" />
    </svg>
  );
}
