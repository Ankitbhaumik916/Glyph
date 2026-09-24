"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Liquid wave loader.
 *
 * Seven bars driven by three summed sine waves (a slow primary swell, a faster
 * bounce, and a fine ripple), with droplets released at the crest.
 *
 * Notes on the adaptations from the source component:
 * - "use client" and a mounted guard, because this renders inside a Next.js
 *   server-rendered tree and the wave is a function of Date.now().
 * - role="status" with a label, so a screen reader announces the wait instead
 *   of seeing a pile of empty divs.
 * - A still frame under prefers-reduced-motion; a 31fps wave is exactly what
 *   that setting exists to stop.
 * - Colours are a prop. "spectrum" is the original rainbow; "brand" keeps to
 *   the app's midnight/lilac palette.
 */

const PALETTES = {
  spectrum: [
    "from-purple-500 to-pink-500",
    "from-blue-500 to-purple-500",
    "from-cyan-400 to-blue-500",
    "from-green-400 to-cyan-400",
    "from-yellow-400 to-green-400",
    "from-orange-400 to-yellow-400",
    "from-red-500 to-orange-400",
  ],
  brand: [
    "from-violet-500 to-fuchsia-400",
    "from-indigo-500 to-violet-500",
    "from-sky-500 to-indigo-500",
    "from-cyan-400 to-sky-500",
    "from-indigo-400 to-cyan-400",
    "from-violet-400 to-indigo-400",
    "from-fuchsia-400 to-violet-400",
  ],
} as const;

/** Glow colour per bar, matched to the gradient above it. */
const GLOWS = {
  spectrum: ["#a855f7", "#3b82f6", "#06b6d4", "#10b981", "#eab308", "#f97316", "#ef4444"],
  brand: ["#a78bfa", "#818cf8", "#38bdf8", "#22d3ee", "#60a5fa", "#a5b4fc", "#e879f9"],
} as const;

// A bar with negative height is flipped and drawn BELOW its own box, outside
// the flex line. The container is sized so the deepest possible excursion
// (half the column, plus a full MAX_HEIGHT below it) still lands inside:
// 150 centre + 56 half-column + 80 swing = 286 < 300. Without that reservation
// the wave overlaps whatever follows it.
const BARS = 7;
const MAX_HEIGHT = 80;
const FRAME_MS = 32;

export type LiquidLoadingProps = {
  palette?: keyof typeof PALETTES;
  className?: string;
  /** Announced to assistive tech, and used as the visually hidden label. */
  label?: string;
  /**
   * "block" is the full standalone wave. "inline" is a compact five-bar
   * version sized to sit inside a button next to its label: no droplets, and
   * bars grow from the centre rather than flipping below the baseline, which
   * would spill outside the button.
   */
  variant?: "block" | "inline";
};

export default function LiquidLoading({
  palette = "brand",
  className = "",
  label = "Working…",
  variant = "block",
}: LiquidLoadingProps) {
  if (variant === "inline") {
    return <InlineWave palette={palette} className={className} />;
  }
  const colors = PALETTES[palette];
  const glows = GLOWS[palette];

  const [heights, setHeights] = useState<number[]>(() => Array(BARS).fill(0));
  const [droplets, setDroplets] = useState<boolean[]>(() => Array(BARS).fill(false));
  // One clock shared by every element in a frame, so the bars, droplets and
  // highlights stay in step instead of each reading Date.now() separately.
  const [clock, setClock] = useState(0);
  const reduced = useRef(false);

  useEffect(() => {
    reduced.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced.current) {
      // A still, pleasant frame rather than a frozen flat line.
      setHeights(Array.from({ length: BARS }, (_, i) => MAX_HEIGHT * Math.sin(i * 0.8)));
      return;
    }

    const interval = window.setInterval(() => {
      const time = Date.now() * 0.001;
      setClock(time);
      setHeights(
        Array.from({ length: BARS }, (_, index) => {
          const delay = index * 0.8;
          const primaryWave = Math.sin(time + delay);
          const bounceWave = Math.sin(time * 4 + delay) * 0.15;
          const ripple = Math.sin(time * 8 + delay) * 0.05;
          return MAX_HEIGHT * (primaryWave + bounceWave + ripple);
        }),
      );
      setDroplets(
        Array.from({ length: BARS }, (_, index) => Math.sin(time + index * 0.8) > 0.8),
      );
    }, FRAME_MS);

    return () => window.clearInterval(interval);
  }, []);

  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex h-[300px] items-center justify-center gap-4 ${className}`}
    >
      {heights.map((height, index) => (
        <div key={index} className="relative flex flex-col items-center">
          {/* Droplet, released at the crest of the wave */}
          <div
            className={`mb-3 h-4 w-4 rounded-full bg-gradient-to-r ${colors[index]} transition-all duration-500 ease-out ${
              droplets[index] ? "opacity-100" : "opacity-0"
            }`}
            style={{
              filter: "blur(0.5px)",
              transform: droplets[index]
                ? `translateY(${Math.sin(clock * 8 + index * 0.5) * 3}px) scale(${
                    0.8 + Math.sin(clock * 6 + index * 0.3) * 0.4
                  })`
                : "translateY(10px) scale(0.5)",
              boxShadow: droplets[index] ? `0 0 15px ${glows[index]}40` : "none",
            }}
          />

          {/* The bar itself */}
          <div
            className={`relative w-10 overflow-hidden rounded-full bg-gradient-to-t ${colors[index]} shadow-lg transition-all duration-200 ease-out`}
            style={{
              height: `${Math.abs(height)}px`,
              transform: height < 0 ? "scaleY(-1)" : "scaleY(1)",
              transformOrigin: "bottom",
              filter: "blur(0.3px)",
              boxShadow: `0 0 20px ${glows[index]}50, inset 0 0 20px rgba(255,255,255,0.1)`,
            }}
          >
            {/* Surface tension */}
            <div
              className="absolute left-0 right-0 top-0 h-4 rounded-full bg-gradient-to-b from-white/40 to-transparent"
              style={{
                transform: `translateY(${Math.sin(clock * 3 + index * 0.5) * 1}px) scaleY(${
                  0.8 + Math.sin(clock * 4 + index * 0.3) * 0.3
                })`,
              }}
            />
            {/* Body sheen */}
            <div
              className="absolute inset-0 rounded-full"
              style={{
                transform: `translateY(${Math.sin(clock * 2 + index * 0.5) * 2}px)`,
                background:
                  "linear-gradient(0deg, rgba(255,255,255,0.3) 0%, rgba(255,255,255,0.1) 50%, transparent 100%)",
              }}
            />
            {/* Shimmer travelling across the bar */}
            <div
              className="absolute inset-0 rounded-full bg-gradient-to-r from-transparent via-white/40 to-transparent"
              style={{
                transform: `translateX(${Math.sin(clock * 1.5 + index * 0.7) * 8}px)`,
                width: "140%",
                left: "-20%",
              }}
            />
            {/* Rising bubble */}
            <div
              className="absolute h-2 w-2 rounded-full bg-white/30"
              style={{
                top: `${20 + Math.sin(clock * 3 + index * 0.8) * 10}%`,
                left: `${30 + Math.sin(clock * 2 + index * 0.6) * 20}%`,
                transform: `scale(${0.5 + Math.sin(clock * 4 + index * 0.4) * 0.5})`,
                opacity: Math.sin(clock * 5 + index * 0.9) * 0.3 + 0.3,
              }}
            />
          </div>

          {/* Pooled droplet at the base */}
          <div
            className={`mt-2 h-3 w-3 rounded-full bg-gradient-to-r ${colors[index]} transition-all duration-300`}
            style={{
              opacity: Math.sin(clock * 3 + index * 0.9) * 0.4 + 0.6,
              transform: `scale(${0.6 + Math.sin(clock * 2 + index * 0.6) * 0.4}) translateY(${
                Math.sin(clock * 4 + index * 0.8) * 1
              }px)`,
              filter: "blur(0.2px)",
              boxShadow: `0 2px 8px ${glows[index]}40`,
            }}
          />
        </div>
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}

const INLINE_BARS = 5;
const INLINE_MAX = 16; // px, fits a 44-48px tall button with room to spare

/**
 * Compact wave for use inside a button, beside its label.
 *
 * Same maths as the block version, but bars grow symmetrically from the centre
 * instead of flipping below the baseline - a flipped bar draws outside its own
 * box and would hang out of the button. Decorative here: the button's own text
 * ("Analysing signatures…") is what announces the state, so this is hidden
 * from assistive tech rather than being a second live region.
 */
function InlineWave({
  palette,
  className = "",
}: {
  palette: keyof typeof PALETTES;
  className?: string;
}) {
  const colors = PALETTES[palette];
  const [heights, setHeights] = useState<number[]>(() => Array(INLINE_BARS).fill(INLINE_MAX * 0.4));

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setHeights(Array.from({ length: INLINE_BARS }, (_, i) => INLINE_MAX * (0.45 + 0.2 * Math.sin(i))));
      return;
    }
    const interval = window.setInterval(() => {
      const time = Date.now() * 0.001;
      setHeights(
        Array.from({ length: INLINE_BARS }, (_, index) => {
          const delay = index * 0.8;
          const wave =
            Math.sin(time + delay) +
            Math.sin(time * 4 + delay) * 0.15 +
            Math.sin(time * 8 + delay) * 0.05;
          // |wave| keeps every bar visible; the floor stops it collapsing to nothing.
          return Math.max(INLINE_MAX * 0.22, INLINE_MAX * Math.abs(wave));
        }),
      );
    }, FRAME_MS);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <span
      aria-hidden="true"
      className={`inline-flex h-5 shrink-0 items-center gap-[3px] ${className}`}
    >
      {heights.map((height, index) => (
        <span
          key={index}
          className={`w-[5px] rounded-full bg-gradient-to-t ${colors[index]} transition-[height] duration-200 ease-out`}
          style={{ height: `${height}px` }}
        />
      ))}
    </span>
  );
}
