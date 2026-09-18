"use client";

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
      <figcaption className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </figcaption>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`data:image/png;base64,${base64}`}
        alt={`Preprocessed ${label} signature as seen by the model`}
        width={155}
        height={155}
        className="h-40 w-40 rounded-md border border-slate-300 bg-black object-contain"
        style={{ imageRendering: "pixelated" }}
      />
    </figure>
  );
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 font-mono text-lg font-semibold text-slate-900">{value}</dd>
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

  const verdictStyle = is_borderline
    ? "border-amber-300 bg-amber-50 text-amber-900"
    : is_genuine
      ? "border-green-300 bg-green-50 text-green-900"
      : "border-red-300 bg-red-50 text-red-900";
  const markerStyle = is_borderline
    ? "bg-amber-500"
    : is_genuine
      ? "bg-green-600"
      : "bg-red-600";
  const verdictText = is_borderline
    ? "TOO CLOSE TO CALL"
    : is_genuine
      ? "LIKELY AUTHENTIC"
      : "LIKELY FORGED";

  return (
    <section aria-live="polite" className="space-y-6">
      <div className={`rounded-xl border-2 px-6 py-5 ${verdictStyle}`}>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest opacity-70">
              Verdict
            </p>
            <p className="mt-1 text-3xl font-bold tracking-tight">{verdictText}</p>
          </div>
          <div className="text-right">
            <p className="text-xs font-semibold uppercase tracking-widest opacity-70">
              Margin
            </p>
            <p className="mt-1 font-mono text-3xl font-bold">
              {(confidence * 100).toFixed(1)}%
            </p>
          </div>
        </div>
        {is_borderline && (
          <p className="mt-4 border-t border-amber-200 pt-3 text-sm">
            The distance is within {borderline_band.toFixed(2)} of the threshold
            {is_genuine ? " (just inside)" : " (just outside)"}. At this range the verdict is
            not reproducible - re-drawing the boxes can flip it. Treat this as inconclusive
            and get a second signature pair or an expert opinion.
          </p>
        )}
      </div>

      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <Stat label="Distance" value={distance.toFixed(4)} sub="Euclidean, embedding space" />
        <Stat label="Threshold" value={threshold.toFixed(4)} sub="Genuine when distance is at or below" />
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
              ? `Spread over ${variants} crop margins${
                  variant_spread > 0.2 ? " - high, check the previews" : ""
                }`
              : "Draw a box to average over crops"
          }
        />
      </dl>

      {/* Distance on its true scale: 0 to the max possible distance between two
          L2-normalized embeddings, with the decision threshold marked. */}
      <div className="rounded-lg border border-slate-200 bg-white px-5 py-4">
        <div className="mb-3 flex items-center justify-between text-xs font-medium text-slate-500">
          <span>0.00 (identical)</span>
          <span>{max_distance.toFixed(2)} (maximally different)</span>
        </div>
        <div className="relative h-3 w-full rounded-full bg-slate-200">
          <div
            className="absolute inset-y-0 left-0 rounded-l-full bg-green-200"
            style={{ width: `${pct(threshold, max_distance)}%` }}
            aria-hidden="true"
          />
          {/* Inconclusive band: verdicts inside it are not reproducible. */}
          <div
            className="absolute inset-y-0 bg-amber-300"
            style={{
              left: `${pct(threshold - borderline_band, max_distance)}%`,
              width: `${pct(2 * borderline_band, max_distance)}%`,
            }}
            aria-hidden="true"
          />
          <div
            className="absolute -top-1 h-5 w-0.5 bg-slate-900"
            style={{ left: `${pct(threshold, max_distance)}%` }}
            aria-hidden="true"
          />
          <div
            className={`absolute -top-1.5 h-6 w-1.5 -translate-x-1/2 rounded-full ring-2 ring-white ${markerStyle}`}
            style={{ left: `${pct(distance, max_distance)}%` }}
            aria-hidden="true"
          />
        </div>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-600">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-green-200" /> genuine range
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-0.5 bg-slate-900" /> threshold {threshold.toFixed(3)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-amber-300" /> too close to call
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className={`h-2.5 w-2.5 rounded-full ${markerStyle}`} /> this pair{" "}
            {distance.toFixed(3)}
          </span>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-5 py-4">
        <h3 className="text-sm font-semibold text-slate-900">What the model actually saw</h3>
        <p className="mt-1 text-xs text-slate-600">
          Output of the preprocessing pipeline: document localization, CLAHE, Sauvola
          binarization, deskew and stroke normalization, at {" "}
          <span className="font-mono">155&times;155</span>. If these look wrong - cropped to
          the wrong region, missing strokes, heavy speckle - the score is not meaningful.
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-8">
          <PreprocessedImage label="Reference" base64={preprocessed_ref_base64} />
          <PreprocessedImage label="Test" base64={preprocessed_test_base64} />
        </div>
      </div>

      <button
        type="button"
        onClick={onReset}
        className="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-800 transition-colors hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
      >
        Run another comparison
      </button>
    </section>
  );
}
