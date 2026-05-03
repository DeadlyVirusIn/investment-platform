// Phase UI-RESET — core UI primitives.
// Every page builds from these; no ad-hoc styling allowed in pages.

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

// -------------------------------- Card -----------------------------------

export function Card({
  children, className, size = "md", hoverable = false, nonProd = false,
}: {
  children: ReactNode; className?: string;
  size?: "sm" | "md" | "lg";
  hoverable?: boolean; nonProd?: boolean;
}) {
  const sz = { sm: "u-card-tight", md: "u-card", lg: "u-card-lg" }[size];
  return (
    <div className={cn(
      sz, hoverable && "u-card-hover", nonProd && "u-nonprod-ribbon",
      className,
    )}>
      {children}
    </div>
  );
}

// -------------------------------- Label ----------------------------------

export function Label({
  children, small = false, className,
}: {
  children: ReactNode; small?: boolean; className?: string;
}) {
  return (
    <div className={cn(small ? "u-label-sm" : "u-label", className)}>
      {children}
    </div>
  );
}

// -------------------------------- Stat -----------------------------------

export function Stat({
  label, value, sub, tone = "neutral", size = "lg",
}: {
  label: string; value: ReactNode; sub?: ReactNode;
  tone?: "pos" | "neg" | "neutral" | "warn";
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const valueCls = {
    pos: "text-success",
    neg: "text-danger",
    warn: "text-warning",
    neutral: "text-fg",
  }[tone];
  const sizeCls = {
    sm: "u-num-sm", md: "u-num-md",
    lg: "u-num-lg", xl: "u-num-xl",
  }[size];
  return (
    <div>
      <Label>{label}</Label>
      <div className={cn(sizeCls, valueCls, "mt-2")}>{value}</div>
      {sub && <div className="u-caption-2 mt-1.5">{sub}</div>}
    </div>
  );
}

// -------------------------------- Pill -----------------------------------

export type PillTone = "success" | "danger" | "warning" | "accent" | "neutral";

export function Pill({
  tone = "neutral", children, className, dot = false,
}: {
  tone?: PillTone; children: ReactNode; className?: string; dot?: boolean;
}) {
  return (
    <span className={cn(`u-pill u-pill-${tone}`, className)}>
      {dot && <span className={`u-dot u-dot-${tone}`} />}
      {children}
    </span>
  );
}

// -------------------------- Non-production marker -----------------------

export function NonProdBadge({ className }: { className?: string }) {
  return (
    <span className={cn("u-nonprod-label", className)}>
      Not used in production
    </span>
  );
}

// -------------------------------- Empty ---------------------------------

export function EmptyState({
  title, hint, glyph = "◌", cta,
}: {
  title: string; hint?: string; glyph?: string; cta?: ReactNode;
}) {
  return (
    <div className="u-empty">
      <div className="text-fg-4 text-2xl mb-3">{glyph}</div>
      <div className="u-body text-fg font-medium mb-1.5">{title}</div>
      {hint && <div className="u-caption-2 max-w-xs">{hint}</div>}
      {cta && <div className="mt-4">{cta}</div>}
    </div>
  );
}

// -------------------------------- Skeleton ------------------------------

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn(
      "animate-pulse bg-elev rounded-md",
      className ?? "h-6 w-full",
    )} />
  );
}

// -------------------------------- Divider -------------------------------

export function Divider({ vertical = false, className }: {
  vertical?: boolean; className?: string;
}) {
  return <div className={cn(vertical ? "u-divider-v" : "u-divider", className)} />;
}

// -------------------------------- Section header -----------------------

export function SectionHeader({
  title, right, hint,
}: {
  title: string; right?: ReactNode; hint?: string;
}) {
  return (
    <div className="flex items-end justify-between mb-4">
      <div>
        <Label>{title}</Label>
        {hint && <div className="u-caption-2 mt-1">{hint}</div>}
      </div>
      {right && <div>{right}</div>}
    </div>
  );
}

// -------------------------------- Tone helpers --------------------------

export function toneForNumber(n: number | null | undefined): "pos" | "neg" | "neutral" {
  if (n === null || n === undefined) return "neutral";
  return n > 0 ? "pos" : n < 0 ? "neg" : "neutral";
}

// -------------------------------- Formatters ----------------------------

export function fmtUSD(n: number, digits = 0): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).format(n);
}
export function fmtPct(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined) return "—";
  const s = n > 0 ? "+" : "";
  return `${s}${n.toFixed(digits)}%`;
}
export function fmtSignedUSD(n: number, digits = 2): string {
  const s = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${s}$${Math.abs(n).toFixed(digits)}`;
}
