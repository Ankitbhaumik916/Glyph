"use client";

import { useState } from "react";

import { ApiError, submitReview, type VerifyResult } from "@/lib/api";

const CORRECTNESS = [
  { value: "yes", label: "Yes, it was right" },
  { value: "no", label: "No, it was wrong" },
  { value: "unsure", label: "I don't know" },
] as const;

export default function ReviewForm({ result }: { result: VerifyResult }) {
  const [rating, setRating] = useState(0);
  const [hovered, setHovered] = useState(0);
  const [correct, setCorrect] = useState<"yes" | "no" | "unsure" | null>(null);
  const [comment, setComment] = useState("");
  const [name, setName] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    if (rating === 0) {
      setError("Pick a rating first.");
      return;
    }
    setState("sending");
    setError(null);
    try {
      await submitReview({
        rating,
        verdict_correct: correct,
        comment: comment.trim(),
        name: name.trim(),
        // Carried along so a review is readable without digging up the session.
        distance: result.distance,
        threshold: result.threshold,
        is_genuine: result.is_genuine,
        is_borderline: result.is_borderline,
        variant_spread: result.variant_spread,
      });
      setState("done");
    } catch (err) {
      setState("error");
      setError(
        err instanceof ApiError
          ? err.detail.code === "reviews_unavailable"
            ? "Reviews aren't switched on for this server yet."
            : err.detail.message
          : "Could not send the review.",
      );
    }
  };

  if (state === "done") {
    return (
      <div className="rounded-2xl border border-amber-400/25 bg-amber-400/5 p-6 text-center">
        <p className="text-sm font-semibold text-amber-200">Thanks - that&apos;s recorded.</p>
        <p className="mt-1 text-xs text-slate-400">
          Your notes go straight to the maintainer and help calibrate the model.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
      <h3 className="text-sm font-semibold text-white">How did this comparison go?</h3>
      <p className="mt-1 text-xs text-slate-400">
        Only the maintainer sees these. It is the fastest way to tell us the model was
        wrong about a pair you know.
      </p>

      <div className="mt-5 flex items-center gap-1" role="radiogroup" aria-label="Rating out of 5">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={rating === n}
            aria-label={`${n} star${n > 1 ? "s" : ""}`}
            onClick={() => {
              setRating(n);
              setError(null);
            }}
            onMouseEnter={() => setHovered(n)}
            onMouseLeave={() => setHovered(0)}
            className="rounded p-1 transition-transform hover:scale-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
          >
            <svg
              viewBox="0 0 24 24"
              className={`h-7 w-7 ${
                n <= (hovered || rating) ? "fill-amber-400 text-amber-400" : "fill-transparent text-slate-600"
              }`}
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.5 9.7l5.9-.9z"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        ))}
      </div>

      <fieldset className="mt-6">
        <legend className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Was the verdict correct?
        </legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {CORRECTNESS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setCorrect(correct === option.value ? null : option.value)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                correct === option.value
                  ? "border-amber-400 bg-amber-400/15 text-amber-200"
                  : "border-white/15 text-slate-300 hover:border-white/30"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </fieldset>

      <label className="mt-6 block">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Anything else? (optional)
        </span>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="What you expected, what looked off, what the preview showed…"
          className="mt-2 w-full resize-y rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-amber-400/50 focus:outline-none"
        />
      </label>

      <label className="mt-4 block">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Your name (optional)
        </span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={120}
          className="mt-2 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-amber-400/50 focus:outline-none"
          placeholder="So we can follow up"
        />
      </label>

      {error && <p className="mt-4 text-xs text-red-400">{error}</p>}

      <button
        type="button"
        onClick={send}
        disabled={state === "sending"}
        className="mt-5 w-full rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-amber-200 disabled:cursor-not-allowed disabled:bg-slate-600 disabled:text-slate-300"
      >
        {state === "sending" ? "Sending…" : "Submit review"}
      </button>
    </div>
  );
}
