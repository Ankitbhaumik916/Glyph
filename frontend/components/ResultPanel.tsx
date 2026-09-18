"use client";

import ReviewForm from "@/components/ReviewForm";
import type { VerifyResult } from "@/lib/api";

interface Props {
  result: VerifyResult;
  onReset: () => void;
}

function pct(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.min(100, Math.max(0, (value / max) * 100));
}

/** The 155x155 preprocessed image, exactly as the model received it. */
function PreprocessedImage({ label, base64 }: { label: string; base64: string }) {
  return (
    <figure className="flex flex-col items-center">
      <figcaption className="mb-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
        {label}
      </figcaption>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`data:image/png;base64,${base64}`}
        alt={`Preprocessed ${label} signature as seen by the model`}
        width={155}
        height={155}
        className="h-40 w-40 rounded-lg border border-white/10 bg-black object-contain"
        style={{ imageRendering: "pixelated" }}
      />
    </figure>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 font-mono text-lg font-semibold text-white">{value}</dd>
      {sub ? <p className="mt-0.5 text-xs text-slate-500">{sub}</p> : null}
    </div>
  );
}

export default function ResultPanel({ result, onReset }: Props) {
  const {
    distance,
    threshold,
    max_distance,
    is_genuine,
    is_borderline,
    borderline_band,
    variants,
    variant_spread,
    confidence,
    preprocessed_ref_base64,
    preprocessed_test_base64,
  } = result;

  const tone = is_borderline
    ? {
        frame: "border-amber-400/40 bg-amber-400/[0.07]",
        text: "text-amber-200",
        marker: "bg-amber-400",
        label: "TOO CLOSE TO CALL",
      }
    : is_genuine
      ? {
          frame: "border-emerald-400/40 bg-emerald-400/[0.07]",
          text: "text-emerald-300",
          marker: "bg-emerald-400",
          label: "LIKELY AUTHENTIC",
        }
      : {
          frame: "border-red-400/40 bg-red-400/[0.07]",
          text: "text-red-300",
          marker: "bg-red-400",
          label: "LIKELY FORGED",
        };

  return (
    <section aria-live="polite" className="space-y-6">
      <div className={`rounded-2xl border px-6 py-6 ${tone.frame}`}>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-slate-400">
              Verdict
            </p>
            <p className={`mt-2 text-3xl font-bold tracking-tight sm:text-4xl ${tone.text}`}>
              {tone.label}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-slate-400">
              Margin
            </p>
            <p className="mt-2 font-mono text-3xl font-bold text-white">
              {(confidence * 100).toFixed(1)}%
            </p>
          </div>
        </div>
        {is_borderline && (
          <p className="mt-5 border-t border-white/10 pt-4 text-sm text-amber-100/90">
            The distance is within {borderline_band.toFixed(2)} of the threshold
            {is_genuine ? " (just inside)" : " (just outside)"}. At this range the verdict is
            not reproducible - re-drawing the boxes can flip it. Treat it as inconclusive and
            get a second reference or an expert opinion.
          </p>
        )}
      </div>

      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <Stat label="Distance" value={distance.toFixed(4)} sub="Euclidean, embedding space" />
        <Stat label="Threshold" value={threshold.toFixed(4)} sub="Genuine at or below" />
        <Stat
          label="Margin"
          value={`${(confidence * 100).toFixed(1)}%`}
          sub="Distance from the boundary, not a probability"
        />
        <Stat
          label="Crop sensitivity"
          value={variants > 1 ? variant_spread.toFixed(3) : "n/a"}
          sub={
            variants > 1
              ? `Spread over ${variants} crop margins${variant_spread > 0.2 ? " - high" : ""}`
              : "Draw a box to average over crops"
          }
        />
      </dl>

      {/* Distance on its true scale, with the threshold and inconclusive band marked. */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-5">
        <div className="mb-3 flex items-center justify-between text-xs text-slate-500">
          <span>0.00 (identical)</span>
          <span>{max_distance.toFixed(2)} (maximally different)</span>
        </div>
        <div className="relative h-3 w-full rounded-full bg-white/10">
          <div
            className="absolute inset-y-0 left-0 rounded-l-full bg-emerald-400/25"
            style={{ width: `${pct(threshold, max_distance)}%` }}
            aria-hidden="true"
          />
          <div
            className="absolute inset-y-0 bg-amber-400/40"
            style={{
              left: `${pct(threshold - borderline_band, max_distance)}%`,
              width: `${pct(2 * borderline_band, max_distance)}%`,
            }}
            aria-hidden="true"
          />
          <div
            className="absolute -top-1 h-5 w-0.5 bg-white"
            style={{ left: `${pct(threshold, max_distance)}%` }}
            aria-hidden="true"
          />
          <div
            className={`absolute -top-1.5 h-6 w-1.5 -translate-x-1/2 rounded-full ring-2 ring-ink ${tone.marker}`}
            style={{ left: `${pct(distance, max_distance)}%` }}
            aria-hidden="true"
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-400">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-emerald-400/25" /> genuine range
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-0.5 bg-white" /> threshold {threshold.toFixed(3)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-amber-400/40" /> too close to call
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className={`h-2.5 w-2.5 rounded-full ${tone.marker}`} /> this pair{" "}
            {distance.toFixed(3)}
          </span>
        </div>
      </div>

      <div className="rounded-2xl border border-white/10 bg-ink-soft px-5 py-5">
        <h3 className="text-sm font-semibold text-white">What the model actually saw</h3>
        <p className="mt-1 text-xs leading-relaxed text-slate-400">
          Output of the preprocessing pipeline - document localization, CLAHE, Sauvola
          binarization, deskew and stroke normalization - at{" "}
          <span className="font-mono">155&times;155</span>. If these look wrong (cropped to the
          wrong region, missing strokes, heavy speckle) the score is not meaningful.
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-8">
          <PreprocessedImage label="Reference" base64={preprocessed_ref_base64} />
          <PreprocessedImage label="Test" base64={preprocessed_test_base64} />
        </div>
      </div>

      <ReviewForm result={result} />

      <button
        type="button"
        onClick={onReset}
        className="w-full rounded-full border border-white/15 px-4 py-3 text-sm font-semibold text-slate-200 transition-colors hover:bg-white/5"
      >
        Run another comparison
      </button>
    </section>
  );
}
