"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, verifySignatures, type VerifyResult } from "@/lib/api";

/**
 * "See a live result": runs a real comparison against the live backend using a
 * bundled pair of signatures.
 *
 * Deliberately not canned output - the label promises a live result, so it
 * makes the actual call, and shows the same preprocessed images and numbers the
 * tester would. It also doubles as a health check anyone can run from the
 * landing page.
 */
export default function DemoOverlay({ onClose }: { onClose: () => void }) {
  const [state, setState] = useState<"loading" | "done" | "error">("loading");
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [message, setMessage] = useState("");
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const run = useCallback(async (signal?: AbortSignal) => {
    setState("loading");
    try {
      const [a, b] = await Promise.all([
        fetch("/demo/sample-reference.jpg", { signal }).then((r) => r.blob()),
        fetch("/demo/sample-test.jpg", { signal }).then((r) => r.blob()),
      ]);
      const data = await verifySignatures(
        new File([a], "sample-reference.jpg", { type: "image/jpeg" }),
        new File([b], "sample-test.jpg", { type: "image/jpeg" }),
        { reference: null, test: null },
        signal,
      );
      setResult(data);
      setState("done");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setState("error");
      setMessage(
        err instanceof ApiError
          ? `${err.detail.message} The backend may be asleep - try again in a moment.`
          : "Could not reach the backend.",
      );
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void run(controller.signal);
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      controller.abort();
      document.removeEventListener("keydown", onKey);
    };
  }, [run, onClose]);

  const verdict = result
    ? result.is_borderline
      ? { label: "TOO CLOSE TO CALL", tone: "text-amber-200 border-amber-300/40 bg-amber-300/10" }
      : result.is_genuine
        ? { label: "LIKELY AUTHENTIC", tone: "text-emerald-200 border-emerald-300/40 bg-emerald-300/10" }
        : { label: "LIKELY FORGED", tone: "text-red-200 border-red-300/40 bg-red-300/10" }
    : null;

  return (
    <div
      className="demo-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="A live comparison of two sample signatures"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="demo-panel" ref={panelRef}>
        <div className="demo-head">
          <div>
            <p className="demo-eyebrow">Live comparison</p>
            <h2 className="demo-title">Two sample signatures, scored just now</h2>
          </div>
          <button ref={closeRef} type="button" className="demo-close" onClick={onClose} aria-label="Close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {state === "loading" && (
          <p className="demo-status">
            Running the comparison on the live model… if the server has been idle this can
            take a moment to wake.
          </p>
        )}

        {state === "error" && (
          <div className="demo-status demo-error">
            <p>{message}</p>
            <button type="button" className="demo-retry" onClick={() => void run()}>
              Try again
            </button>
          </div>
        )}

        {state === "done" && result && verdict && (
          <>
            <div className={`demo-verdict ${verdict.tone}`}>
              <span>{verdict.label}</span>
              <span className="demo-distance">
                distance {result.distance.toFixed(4)} · threshold {result.threshold.toFixed(4)}
              </span>
            </div>

            <p className="demo-copy">
              This is what the model actually received - the photos reduced to 155&times;155
              binarized strokes. If these look wrong, the score means nothing, which is why
              the tester shows them every time.
            </p>

            <div className="demo-images">
              {[
                { label: "Reference", b64: result.preprocessed_ref_base64 },
                { label: "Test", b64: result.preprocessed_test_base64 },
              ].map((img) => (
                <figure key={img.label}>
                  <figcaption>{img.label}</figcaption>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`data:image/png;base64,${img.b64}`}
                    alt={`Preprocessed ${img.label.toLowerCase()} signature`}
                    style={{ imageRendering: "pixelated" }}
                  />
                </figure>
              ))}
            </div>

            {/* Both samples are genuinely from the same person, so the honest
                gloss depends on what the model just said - including when it
                gets this pair wrong. */}
            <p className="demo-note">
              Both samples are genuine signatures from the same person.{" "}
              {result.is_borderline
                ? "This pair landed inside the inconclusive band, where re-drawing a crop can flip the verdict - an honest look at where the model is weakest."
                : result.is_genuine
                  ? "Here the model agreed, with a margin of " +
                    (result.threshold - result.distance).toFixed(3) +
                    " to spare."
                  : "The model got this one wrong, which it does for roughly one comparison in five."}
            </p>
          </>
        )}

        <Link href="/verify" className="demo-cta">
          Test your own signatures
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} aria-hidden="true">
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Link>
      </div>
    </div>
  );
}
