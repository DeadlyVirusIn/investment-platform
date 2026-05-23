import { cn } from '@/lib/cn';
import type { DecisionStep } from '../data/journal-data';

const STEPS: DecisionStep[] = ["Idea", "Thesis", "Catalyst", "Position", "Outcome", "Lesson"];

export function SixStepRibbon({
  current,
  className,
  size = "md",
}: {
  current: DecisionStep;
  className?: string;
  size?: "sm" | "md";
}) {
  const currentIdx = STEPS.indexOf(current);
  return (
    <ol
      className={cn(
        "flex items-center gap-1.5 w-full",
        size === "sm" ? "text-[9.5px]" : "text-[10.5px]",
        className,
      )}
      aria-label={`Decision step: ${current}`}
    >
      {STEPS.map((step, i) => {
        const state = i < currentIdx ? "done" : i === currentIdx ? "current" : "upcoming";
        return (
          <li key={step} className="flex-1 flex flex-col gap-1 items-stretch">
            <span
              className={cn(
                "h-[3px] rounded-full transition-colors",
                state === "done" && "bg-brand",
                state === "current" && "bg-brand",
                state === "upcoming" && "bg-ink/10",
              )}
            />
            <span
              className={cn(
                "font-semibold uppercase tracking-[0.12em] truncate",
                state === "current" ? "text-brand" : state === "done" ? "text-ink/70" : "text-ink/30",
              )}
            >
              {step}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
