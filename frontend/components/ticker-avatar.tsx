import { cn } from "@/lib/utils";

const HUES = [274, 300, 220, 160, 30, 350, 190];

function hueFor(ticker: string) {
  let hash = 0;
  for (const char of ticker) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return HUES[hash % HUES.length];
}

/** Deterministic gradient tile so each company is recognisable at a glance. */
export function TickerAvatar({
  ticker,
  className,
}: {
  ticker: string;
  className?: string;
}) {
  const hue = hueFor(ticker);
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-9 shrink-0 items-center justify-center rounded-lg text-[0.65rem] font-semibold tracking-tight text-white shadow-sm",
        className,
      )}
      style={{
        backgroundImage: `linear-gradient(135deg, oklch(0.62 0.19 ${hue}), oklch(0.5 0.2 ${hue + 30}))`,
      }}
    >
      {ticker.slice(0, 4)}
    </span>
  );
}
