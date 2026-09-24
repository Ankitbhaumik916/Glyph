"use client";

import type { ForensicAnalysis } from "@/lib/api";

/**
 * Supporting visual analysis.
 *
 * Presentation rules that are not cosmetic:
 * - the heading states plainly that none of this is used in the verdict, so a
 *   reader (including a legal one) cannot mistake it for evidence;
 * - the summary number is labelled and placed as a secondary figure, never
 *   blended with the confidence shown above it;
 * - an unmeasurable feature reads "not measurable", not 0. A feature that
 *   always fails is indistinguishable from a real mismatch otherwise.
 */
const LABELS: Record<string, string> = {
  line_quality: "Line quality",
  stroke_direction: "Stroke direction",
  size_proportion: "Size & proportion",
  alignment_slant: "Alignment & slant",
  proportion_spacing: "Proportion & spacing",
};

/** Driven by the response, not a hard-coded list: a feature retired on the
 *  backend then disappears here instead of rendering as "not measurable". */
function orderFor(forensic: ForensicAnalysis): string[] {
  return Object.keys(LABELS).filter((key) => key in forensic.scores);
}

export default function ForensicPanel({ forensic }: { forensic: ForensicAnalysis }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">
          Supporting visual analysis{" "}
          <span className="font-normal text-slate-400">(not used in the verdict)</span>
        </h3>
        {forensic.mean_score !== null && (
          <p className="text-xs text-slate-500">
            Mean of measured features{" "}
            <span className="font-mono text-slate-300">
              {(forensic.mean_score * 100).toFixed(0)}%
            </span>{" "}
            &middot; separate from the confidence above
          </p>
        )}
      </div>

      <p className="mt-2 text-xs leading-relaxed text-slate-400">
        Classical image measurements comparing the two signatures, shown to explain what
        they have in common and where they differ. They are computed independently of the
        model and do not affect the distance, the threshold or the verdict. Each one was
        kept only if a change of writer moves it more than lighting, resolution or photo
        angle do - but they still separate writers weakly, so read them as description,
        not proof.
      </p>

      <dl className="mt-5 space-y-2.5">
        {orderFor(forensic).map((key) => {
          const value = forensic.scores[key];
          return (
            <div key={key} className="flex items-center gap-3">
              <dt className="w-44 shrink-0 text-xs text-slate-300">{LABELS[key]}</dt>
              <dd className="flex min-w-0 flex-1 items-center gap-3">
                <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/10">
                  {value !== null && (
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-400/70 to-violet-300/80"
                      style={{ width: `${Math.round(value * 100)}%` }}
                    />
                  )}
                </div>
                <span
                  className={`w-28 shrink-0 text-right font-mono text-xs ${
                    value === null ? "text-slate-600" : "text-slate-300"
                  }`}
                >
                  {value === null ? "not measurable" : value.toFixed(3)}
                </span>
              </dd>
            </div>
          );
        })}
      </dl>

      <p className="mt-4 text-[11px] leading-relaxed text-slate-500">
        {forensic.measured} of {forensic.total} features measurable for this pair. Scores
        run 0 to 1, higher meaning more alike. Pen pressure, pen lift, writing speed and
        tremor are deliberately absent: a still photo carries no timing signal, and ink
        density is confounded by pen, paper and lighting. Terminal strokes and letter
        formation were both built and then dropped - the first moved further under a
        10&deg; photo rotation than under a change of writer, the second barely
        responded to a change of writer at all.
      </p>
    </section>
  );
}
