"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import ResultPanel from "@/components/ResultPanel";
import SignatureDropzone from "@/components/SignatureDropzone";
import {
  ApiError,
  API_URL,
  fetchHealth,
  verifySignatures,
  type ApiErrorDetail,
  type CropBox,
  type HealthResult,
  type VerifyResult,
} from "@/lib/api";

const DISCLAIMER =
  "Research prototype - use as a decision-support signal alongside expert review, not a sole determinant.";

function BackendStatus({ health }: { health: HealthResult | null | "error" }) {
  if (health === null) {
    return <span className="text-xs text-slate-400">checking backend&hellip;</span>;
  }
  if (health === "error") {
    return (
      <span className="inline-flex items-center gap-2 text-xs font-medium text-red-700">
        <span className="h-2 w-2 rounded-full bg-red-500" />
        backend unreachable at {API_URL}
      </span>
    );
  }
  if (!health.model_loaded) {
    return (
      <span className="inline-flex items-center gap-2 text-xs font-medium text-amber-700">
        <span className="h-2 w-2 rounded-full bg-amber-500" />
        backend up, model not loaded
      </span>
    );
  }
  const calibrated = health.threshold_source === "calibrated";
  return (
    <span
      className="inline-flex items-center gap-2 text-xs font-medium text-slate-600"
      title={
        calibrated
          ? `Calibrated on local data (bundle default was ${health.bundle_threshold?.toFixed(4)})`
          : "Threshold shipped with the model bundle; run tools/calibrate.py to fit your own"
      }
    >
      <span className="h-2 w-2 rounded-full bg-green-500" />
      model ready &middot; threshold {health.threshold?.toFixed(4)}
      <span
        className={`rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${
          calibrated ? "bg-green-100 text-green-800" : "bg-slate-200 text-slate-600"
        }`}
      >
        {calibrated ? "calibrated" : "bundle default"}
      </span>
      &middot; {health.img_size}px &middot; {health.embed_dim}-d
    </span>
  );
}

export default function Home() {
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [testFile, setTestFile] = useState<File | null>(null);
  const [referenceCrop, setReferenceCrop] = useState<CropBox | null>(null);
  const [testCrop, setTestCrop] = useState<CropBox | null>(null);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<ApiErrorDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [health, setHealth] = useState<HealthResult | null | "error">(null);
  const abortRef = useRef<AbortController | null>(null);

  // Surface a down backend before the user bothers uploading anything.
  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(setHealth)
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setHealth("error");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  const canSubmit = Boolean(referenceFile && testFile) && !isLoading;

  const handleSubmit = useCallback(async () => {
    if (!referenceFile || !testFile) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await verifySignatures(
        referenceFile,
        testFile,
        { reference: referenceCrop, test: testCrop },
        controller.signal,
      );
      setResult(data);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(
        err instanceof ApiError
          ? err.detail
          : { code: "unknown", message: "Unexpected error running the comparison." },
      );
    } finally {
      if (!controller.signal.aborted) setIsLoading(false);
    }
  }, [referenceFile, testFile, referenceCrop, testCrop]);

  const handleReset = useCallback(() => {
    abortRef.current?.abort();
    setReferenceFile(null);
    setTestFile(null);
    setReferenceCrop(null);
    setTestCrop(null);
    setResult(null);
    setError(null);
    setIsLoading(false);
  }, []);

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
      <header className="mb-8 border-b border-slate-200 pb-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Glyph
              <span className="ml-2 align-middle text-sm font-medium text-slate-500">
                signature verification
              </span>
            </h1>
            <p className="mt-1 text-sm text-slate-600">
              Compare a test signature against a known-genuine reference.
            </p>
          </div>
          <BackendStatus health={health} />
        </div>
        <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {DISCLAIMER}
        </p>
      </header>

      {!result && (
        <section>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <SignatureDropzone
              label="Reference signature"
              hint="known genuine"
              field="reference"
              file={referenceFile}
              onFileChange={(file) => {
                setReferenceFile(file);
                setError(null);
              }}
              crop={referenceCrop}
              onCropChange={(crop) => {
                setReferenceCrop(crop);
                setError(null);
              }}
              disabled={isLoading}
              invalid={error?.field === "reference"}
            />
            <SignatureDropzone
              label="Test signature"
              hint="to be checked"
              field="test"
              file={testFile}
              onFileChange={(file) => {
                setTestFile(file);
                setError(null);
              }}
              crop={testCrop}
              onCropChange={(crop) => {
                setTestCrop(crop);
                setError(null);
              }}
              disabled={isLoading}
              invalid={error?.field === "test"}
            />
          </div>

          <p className="mt-4 text-xs text-slate-500">
            Full photos usually work without a box. If a preview shows edges, stripes or
            fingers instead of the signature, drag a box around the signature. Its exact size
            and shape barely matter: the backend re-tightens it to the ink, so a loose box is
            fine as long as nothing else is inside.
          </p>

          {error && (
            <div
              role="alert"
              className="mt-6 rounded-lg border border-red-300 bg-red-50 px-4 py-3"
            >
              <p className="text-sm font-semibold text-red-900">{error.message}</p>
              {error.hint && <p className="mt-1 text-xs text-red-800">{error.hint}</p>}
              <p className="mt-1 font-mono text-[11px] text-red-600">{error.code}</p>
            </div>
          )}

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {isLoading && (
                <svg
                  className="h-4 w-4 animate-spin"
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"
                  />
                </svg>
              )}
              {isLoading ? "Analysing signatures…" : "Verify signature"}
            </button>
            {(referenceFile || testFile) && !isLoading && (
              <button
                type="button"
                onClick={handleReset}
                className="rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
              >
                Clear
              </button>
            )}
          </div>

          {isLoading && (
            <p className="mt-3 text-center text-xs text-slate-500">
              Preprocessing both images and running inference - this usually takes a second
              or two.
            </p>
          )}
        </section>
      )}

      {result && <ResultPanel result={result} onReset={handleReset} />}

      <footer className="mt-10 border-t border-slate-200 pt-4 text-xs text-slate-500">
        <p>{DISCLAIMER}</p>
      </footer>
    </main>
  );
}
