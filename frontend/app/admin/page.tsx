"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import AppHeader from "@/components/AppHeader";
import { useAuth } from "@/components/AuthProvider";
import { ApiError, fetchReviews, type ReviewRecord } from "@/lib/api";

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
  const router = useRouter();
  const { token, email, isAdmin, loading: authLoading } = useAuth();
  const [reviews, setReviews] = useState<ReviewRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (sessionToken: string) => {
    setLoading(true);
    setError(null);
    try {
      setReviews(await fetchReviews({ token: sessionToken }));
    } catch (err) {
      setReviews(null);
      setError(
        err instanceof ApiError
          ? err.detail.code === "forbidden" || err.detail.code === "not_authorized"
            ? "This page is only available to the site owner."
            : err.detail.hint
              ? `${err.detail.message} ${err.detail.hint}`
              : err.detail.message
          : "Could not load reviews.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  // Not signed in at all: send them to sign in and come back.
  useEffect(() => {
    if (!authLoading && !email) router.replace("/login?next=/admin");
  }, [authLoading, email, router]);

  // Signed in as the owner: load without asking for anything else. A
  // non-owner session never issues this request, and would be refused by the
  // server if it did.
  useEffect(() => {
    if (!authLoading && isAdmin && token) void load(token);
  }, [authLoading, isAdmin, token, load]);

  const avg =
    reviews && reviews.length
      ? (reviews.reduce((sum, r) => sum + (r.rating || 0), 0) / reviews.length).toFixed(1)
      : "-";
  const wrong = reviews ? reviews.filter((r) => r.verdict_correct === "no").length : 0;

  return (
    <>
      <AppHeader current="admin" />
      <main className="mx-auto w-full max-w-5xl px-4 pb-20 pt-8 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight text-white">Reviews</h1>
        <p className="mt-1 text-sm text-slate-400">
          Feedback left by testers. Stored in a private dataset repo - this page just reads it.
        </p>

        {authLoading && <p className="mt-8 text-sm text-slate-500">Checking your session&hellip;</p>}

        {/* Signed in, but not the owner. The server would refuse the request
            anyway; this is so the page says something sensible instead of
            sitting empty. */}
        {!authLoading && email && !isAdmin && (
          <div className="mt-8 rounded-xl border border-white/10 bg-white/[0.02] px-5 py-8 text-center">
            <p className="text-sm text-slate-300">This page is only available to the site owner.</p>
            <p className="mt-1 text-xs text-slate-500">Signed in as {email}.</p>
            <Link
              href="/verify"
              className="mt-5 inline-block rounded-full bg-white px-5 py-2 text-xs font-semibold text-ink transition-colors hover:bg-amber-200"
            >
              Back to the tester
            </Link>
          </div>
        )}

        {!authLoading && isAdmin && !reviews && (
          <p className="mt-8 text-sm text-slate-500">
            {loading ? "Loading reviews…" : error ?? "No reviews loaded."}
          </p>
        )}
        {!authLoading && isAdmin && reviews && error && (
          <p className="mt-3 text-xs text-red-400">{error}</p>
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
                  onClick={() => token && void load(token)}
                  className="rounded-full border border-white/15 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-white/5"
                >
                  Refresh
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
