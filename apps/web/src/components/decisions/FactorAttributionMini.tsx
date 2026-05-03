// Factor attribution mini breakdown — 7 signed bars.
// No new layout. Designed to slot under existing audit sections.

import { cn } from "@/lib/cn";

export interface FactorAttribution {
  momentum?: number;
  volatility?: number;
  regime?: number;
  catalyst?: number;
  data_quality?: number;
  risk?: number;
  execution?: number;
  version?: string;
}

const FACTORS: Array<keyof Omit<FactorAttribution, "version" | "raw_inputs">> = [
  "momentum", "volatility", "regime", "catalyst",
  "data_quality", "risk", "execution",
];

export default function FactorAttributionMini({
  attribution,
}: { attribution: FactorAttribution | null | undefined }) {
  if (!attribution) return null;
  return (
    <div>
      <div className="u-label-sm mb-2">Factor attribution</div>
      <div className="space-y-1.5">
        {FACTORS.map(k => {
          const v = (attribution as any)[k] as number | undefined;
          if (v === undefined || v === null) return null;
          return <Row key={k} name={k} value={v} />;
        })}
      </div>
      {attribution.version && (
        <div className="u-caption-2 mt-2 text-fg-3">
          v {attribution.version}
        </div>
      )}
    </div>
  );
}

function Row({ name, value }: { name: string; value: number }) {
  const pct = Math.abs(value) * 100;
  const tone = value > 0.01 ? "pos" : value < -0.01 ? "neg" : "neutral";
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg-2";
  const bar = tone === "pos" ? "bg-success"
    : tone === "neg" ? "bg-danger" : "bg-elev";
  return (
    <div className="grid grid-cols-[120px_1fr_60px] items-center gap-2">
      <span className="u-caption text-fg-2 capitalize">
        {name.replace("_", " ")}
      </span>
      <div className="relative h-1.5 bg-elev rounded-sm overflow-hidden">
        <div className={cn("absolute h-full rounded-sm", bar)}
             style={{
               width: `${Math.min(50, pct / 2)}%`,
               [tone === "neg" ? "right" : "left"]: "50%",
             }} />
        <span className="absolute left-1/2 top-0 bottom-0 w-px bg-b2" />
      </div>
      <span className={cn("u-mono-sm text-right", cls)}>
        {value >= 0 ? "+" : ""}{value.toFixed(2)}
      </span>
    </div>
  );
}
