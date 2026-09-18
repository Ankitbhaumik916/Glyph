"use client";

import { useCallback, useEffect, useState } from "react";

import SiteNav from "@/components/SiteNav";
import { ApiError, fetchReviews, type ReviewRecord } from "@/lib/api";

const KEY_STORAGE = "glyph-admin-key";

function Stars({ n }: { n: number }) {
  return (
    <span className="text-amber-400" aria-label={`${n} out of 5`}>
      {"★".repeat(n)}
      <span className="text-slate-700">{"★".repeat(5 - n)}</span>
    </span>
  );
}

const VERDICT_TONE: Record<string, string> = {
  yes: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  no: "border-red-400/30 bg-red-400/10 text-red-300",
  unsure: "border-white/15 bg-white/5 text-slate-400",
};

export default function AdminPage() {
  const [key, setKey] = useState("");
  const [reviews, setReviews] = useState<ReviewRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (adminKey: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchReviews(adminKey);
      setReviews(data);
      // Session-only: not localStorage, so the key dies with the tab.
      sessionStorage.setItem(KEY_STORAGE, adminKey);
    } catch (err) {
      setReviews(null);
      setError(
        err instanceof ApiError
          ? err.detail.code === "not_authorized"
            ? "That key was rejected."
            : err.detail.message
          : "Could not load reviews.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const saved = sessionStorage.getItem(KEY_STORAGE);
    if (saved) {
      setKey(saved);
      void load(saved);
    }
  }, [load]);

  const signOut = () => {
    sessionStorage.removeItem(KEY_STORAGE);
    setKey("");
    setReviews(null);
  };

  const avg =
    reviews && reviews.length
      ? (reviews.reduce((sum, r) => sum + (r.rating || 0), 0) / reviews.length).toFixed(1)
      : "-";
  const wrong = reviews ? reviews.filter((r) => r.verdict_correct === "no").length : 0;

  return (
    <>
      <SiteNav />
      <main className="mx-auto w-full max-w-5xl px-4 pb-20 pt-28 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight text-white">Reviews</h1>
        <p className="mt-1 text-sm text-slate-400">
          Feedback left by testers. Stored in a private dataset repo - this page just reads it.
        </p>

        {!reviews && (
          <form
            className="mt-8 max-w-sm"
            onSubmit={(e) => {
              e.preventDefault();
              void load(key.trim());
            }}
          >
            <label htmlFor="admin-key" className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Admin key
            </label>
            <input
              id="admin-key"
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              autoComplete="off"
              className="mt-2 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-200 focus:border-amber-400/50 focus:outline-none"
              placeholder="ADMIN_KEY set on the backend"
            />
            <button
              type="submit"
              disabled={loading || !key.trim()}
              className="mt-3 w-full rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-amber-200 disabled:cursor-not-allowed disabled:bg-white/20 disabled:text-slate-500"
            >
              {loading ? "Checking…" : "Unlock"}
            </button>
            {error && <p className="mt-3 text-xs text-red-400">{error}</p>}
          </form>
        )}

        {reviews && (
          <>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              {[
                { label: "Reviews", value: String(reviews.length) },
                { label: "Average rating", value: avg },
                { label: "Reported wrong verdicts", value: String(wrong) },
              ].map((s) => (
                <div key={s.label} className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500">{s.label}</p>
                  <p className="mt-1 font-mono text-lg font-semibold text-white">{s.value}</p>
                </div>
              ))}
              <div className="ml-auto flex gap-2">
                <button
                  type="button"
                  onClick={() => void load(key)}
                  className="rounded-full border border-white/15 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-white/5"
                >
                  Refresh
                </button>
                <button
                  type="button"
                  onClick={signOut}
                  className="rounded-full border border-white/15 px-4 py-2 text-xs font-semibold text-slate-400 hover:bg-white/5"
                >
                  Lock
                </button>
              </div>
            </div>

            {reviews.length === 0 ? (
              <p className="mt-10 rounded-xl border border-white/10 bg-white/[0.02] px-5 py-8 text-center text-sm text-slate-500">
                No reviews yet.
              </p>
            ) : (
              <ul className="mt-6 space-y-3">
                {reviews.map((r) => (
                  <li key={r.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <Stars n={r.rating} />
                        {r.verdict_correct && (
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                              VERDICT_TONE[r.verdict_correct] ?? VERDICT_TONE.unsure
                            }`}
                          >
                            verdict {r.verdict_correct === "yes" ? "correct" : r.verdict_correct === "no" ? "wrong" : "unknown"}
                          </span>
                        )}
                        {r.name && <span className="text-xs text-slate-400">{r.name}</span>}
                      </div>
                      <time className="font-mono text-[11px] text-slate-600">
                        {r.submitted_at?.slice(0, 19).replace("T", " ")} UTC
                      </time>
                    </div>

                    {r.comment && (
                      <p className="mt-3 whitespace-pre-wrap text-sm text-slate-300">{r.comment}</p>
                    )}

                    {typeof r.distance === "number" && (
                      <p className="mt-3 font-mono text-[11px] text-slate-500">
                        distance {r.distance.toFixed(4)} · threshold {r.threshold?.toFixed(4)} ·{" "}
                        {r.is_borderline ? "borderline" : r.is_genuine ? "genuine" : "different"}
                        {typeof r.variant_spread === "number"
                          ? ` · spread ${r.variant_spread.toFixed(3)}`
                          : ""}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </main>
    </>
  );
}
