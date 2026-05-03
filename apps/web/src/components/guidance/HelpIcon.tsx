// Phase SYSTEM-UI-BEGINNER — "?" tooltip icon.

import { useUIMode } from "@/lib/ui/mode";

export default function HelpIcon({ text }: { text: string }) {
  const [mode] = useUIMode();
  if (mode !== "guided") return null;
  return (
    <span className="u-help-icon" title={text} aria-label={text}>?</span>
  );
}
