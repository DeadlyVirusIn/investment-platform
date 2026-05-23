// shadcn Popover adapted to ArthOS V2 token system.
//
// Source: wise-start-bloom-31433ca8/src/components/ui/popover.tsx
// Changes from upstream:
//   - cn import retargeted to '@/lib/cn'
//   - Default content classes use V2 surface/ink/hairline tokens
//     instead of shadcn semantic tokens (bg-popover, border, etc.).
//   - Removed tailwindcss-animate utility classes (animate-in,
//     fade-out-0, zoom, slide). ArthOS V2 doesn't ship the animate
//     plugin; framer-motion handles motion elsewhere. Radix still
//     manages open/close state — just without CSS animation.

import * as React from "react";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { cn } from "@/lib/cn";

const Popover = PopoverPrimitive.Root;
const PopoverTrigger = PopoverPrimitive.Trigger;
const PopoverAnchor = PopoverPrimitive.Anchor;

const PopoverContent = React.forwardRef<
  React.ElementRef<typeof PopoverPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = "center", sideOffset = 4, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      className={cn(
        // V2 tokens — these CSS variables resolve only inside .v2-root.
        // Portal renders outside the v2-root subtree, so we set vars
        // directly via inline style on consumers OR via global fallback.
        // For now, rely on style prop on PopoverContent at call sites
        // OR a body-level fallback (see GlossaryPopover for example).
        "z-50 w-72 rounded-2xl border outline-none p-0 overflow-hidden",
        "bg-[var(--surface-drawer,#18140E)]",
        "text-[var(--ink-primary,#ECE6D8)]",
        "border-[var(--hairline,rgba(236,230,216,0.08))]",
        "shadow-[0_8px_32px_rgba(0,0,0,0.4)]",
        className,
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
));
PopoverContent.displayName = PopoverPrimitive.Content.displayName;

export { Popover, PopoverTrigger, PopoverContent, PopoverAnchor };
