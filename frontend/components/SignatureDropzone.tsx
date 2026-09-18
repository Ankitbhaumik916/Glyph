"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import ReactCrop, { type Crop, type PercentCrop } from "react-image-crop";

import { ApiError, previewSignature, type CropBox, type PreviewResult } from "@/lib/api";

interface Props {
  label: string;
  hint: string;
  field: "reference" | "test";
  file: File | null;
  onFileChange: (file: File | null) => void;
  crop: CropBox | null;
  onCropChange: (crop: CropBox | null) => void;
  disabled?: boolean;
  /** Highlights the box when the backend blamed this specific upload. */
  invalid?: boolean;
}

const ACCEPTED = ["image/png", "image/jpeg", "image/bmp", "image/webp", "image/tiff"];
const PREVIEW_DEBOUNCE_MS = 350;

type PreviewState =
  | { status: "idle" }
  | { status: "loading"; last: PreviewResult | null }
  | { status: "ready"; result: PreviewResult }
  | { status: "error"; message: string };

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** react-image-crop works in percent; the API wants 0-1. */
function toCropBox(c: PercentCrop): CropBox | null {
  if (c.width < 1 || c.height < 1) return null;
  const clamp = (v: number) => Math.min(1, Math.max(0, v / 100));
  return { x: clamp(c.x), y: clamp(c.y), width: clamp(c.width), height: clamp(c.height) };
}

export default function SignatureDropzone({
  label,
  hint,
  field,
  file,
  onFileChange,
  crop,
  onCropChange,
  disabled = false,
  invalid = false,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  // Live crop rectangle while dragging; `crop` (the prop) only updates on release.
  const [draftCrop, setDraftCrop] = useState<Crop | undefined>(undefined);
  const [preview, setPreview] = useState<PreviewState>({ status: "idle" });

  // Object URLs must be revoked or the blobs leak for the life of the page.
  useEffect(() => {
    setDraftCrop(undefined);
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // Keep the drawn rectangle in sync when the parent clears the crop (reset).
  useEffect(() => {
    if (!crop) setDraftCrop(undefined);
  }, [crop]);

  // Ask the backend what the model will see whenever the image or crop settles.
  useEffect(() => {
    if (!file) {
      setPreview({ status: "idle" });
      return;
    }
    const controller = new AbortController();
    setPreview((prev) => ({
      status: "loading",
      last: prev.status === "ready" ? prev.result : prev.status === "loading" ? prev.last : null,
    }));
    const timer = window.setTimeout(() => {
      previewSignature(file, field, crop, controller.signal)
        .then((result) => setPreview({ status: "ready", result }))
        .catch((err) => {
          if (err instanceof DOMException && err.name === "AbortError") return;
          setPreview({
            status: "error",
            message: err instanceof ApiError ? err.detail.message : "Preview failed.",
          });
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [file, crop, field]);

  const accept = useCallback(
    (incoming: File | undefined) => {
      if (!incoming) return;
      if (!ACCEPTED.includes(incoming.type)) {
        setLocalError("Unsupported file type. Use PNG, JPEG, BMP, WEBP or TIFF.");
        return;
      }
      setLocalError(null);
      onCropChange(null);
      onFileChange(incoming);
    },
    [onFileChange, onCropChange],
  );

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    accept(event.dataTransfer.files?.[0]);
  };

  const remove = () => {
    setLocalError(null);
    onCropChange(null);
    onFileChange(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const previewResult =
    preview.status === "ready" ? preview.result : preview.status === "loading" ? preview.last : null;

  return (
    <div className="flex flex-col">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <label htmlFor={inputId} className="text-sm font-semibold text-white">
          {label}
        </label>
        <span className="text-xs text-slate-500">{hint}</span>
      </div>

      {previewUrl ? (
        <div
          className={`overflow-hidden rounded-lg border-2 ${
            invalid ? "border-red-400/60" : "border-white/10"
          } bg-white/[0.03]`}
        >
          <div className="flex min-h-[16rem] items-center justify-center bg-black/50 p-2">
            <ReactCrop
              crop={draftCrop}
              onChange={(_, percent) => setDraftCrop(percent)}
              onComplete={(_, percent) => onCropChange(toCropBox(percent))}
              disabled={disabled}
              keepSelection
              ruleOfThirds={false}
            >
              {/* Plain <img>: a local blob: URL that next/image can't optimise.
                  Browsers apply EXIF orientation here, matching the backend. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewUrl}
                alt={`${label} photo`}
                className="block max-h-[24rem] w-auto max-w-full"
              />
            </ReactCrop>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 px-3 py-2">
            <p className="text-xs text-slate-400">
              {crop ? (
                <>Box drawn &middot; only this area is analysed</>
              ) : (
                <>Drag on the photo to box the signature (optional)</>
              )}
            </p>
            <div className="flex gap-2">
              {crop && !disabled && (
                <button
                  type="button"
                  onClick={() => onCropChange(null)}
                  className="rounded-md px-2 py-1 text-xs font-medium text-slate-300 ring-1 ring-white/15 transition-colors hover:bg-white/10"
                >
                  Clear box
                </button>
              )}
              {!disabled && (
                <>
                  <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    className="rounded-md px-2 py-1 text-xs font-medium text-slate-300 ring-1 ring-white/15 transition-colors hover:bg-white/10"
                  >
                    Replace
                  </button>
                  <button
                    type="button"
                    onClick={remove}
                    aria-label={`Remove ${label}`}
                    className="rounded-md px-2 py-1 text-xs font-medium text-slate-300 ring-1 ring-white/15 transition-colors hover:bg-white/10"
                  >
                    Remove
                  </button>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 border-t border-white/10 bg-black/30 px-3 py-3">
            <div className="relative h-[93px] w-[93px] shrink-0 overflow-hidden rounded border border-white/10 bg-black">
              {previewResult && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`data:image/png;base64,${previewResult.preprocessed_base64}`}
                  alt={`${label} as the model will see it`}
                  className={`h-full w-full ${preview.status === "loading" ? "opacity-40" : ""}`}
                  style={{ imageRendering: "pixelated" }}
                />
              )}
              {preview.status === "loading" && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-amber-300" />
                </div>
              )}
            </div>
            <div className="min-w-0 text-xs">
              <p className="font-semibold text-slate-200">Model input preview</p>
              {preview.status === "error" ? (
                <p className="mt-1 text-red-400">{preview.message}</p>
              ) : previewResult && preview.status === "ready" ? (
                previewResult.signature_detected ? (
                  <p className="mt-1 text-slate-400">
                    Should show only the signature strokes. If it shows edges, stripes or
                    fingers instead, draw a tighter box.
                  </p>
                ) : (
                  <p className="mt-1 font-medium text-amber-300">
                    No signature found{crop ? " inside the box" : ""}. Draw a box around the
                    signature.
                  </p>
                )
              ) : (
                <p className="mt-1 text-slate-500">Processing&hellip;</p>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div
          onClick={() => !disabled && inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              if (!disabled) inputRef.current?.click();
            }
          }}
          onDragOver={(e) => {
            e.preventDefault();
            if (!disabled) setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={onDrop}
          role="button"
          tabIndex={disabled ? -1 : 0}
          aria-label={`${label}: drag and drop an image or press Enter to browse`}
          aria-disabled={disabled}
          className={`flex h-64 cursor-pointer items-center justify-center rounded-lg border-2 border-dashed p-3 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 focus-visible:ring-offset-2 ${
            invalid
              ? "border-red-400/60 bg-red-500/10"
              : isDragging
                ? "border-amber-400/70 bg-amber-400/10"
                : "border-white/15 bg-white/[0.02] hover:border-white/30 hover:bg-white/[0.05]"
          } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
        >
          <div className="pointer-events-none text-center">
            <svg
              className="mx-auto mb-2 h-8 w-8 text-slate-500"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 7.5L12 3m0 0L7.5 7.5M12 3v13.5"
              />
            </svg>
            <p className="text-sm font-medium text-slate-300">
              Drop an image here, or <span className="underline">browse</span>
            </p>
            <p className="mt-1 text-xs text-slate-500">PNG, JPEG, BMP, WEBP or TIFF</p>
          </div>
        </div>
      )}

      <input
        id={inputId}
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(",")}
        className="sr-only"
        disabled={disabled}
        onChange={(e) => accept(e.target.files?.[0])}
      />

      <p className="mt-2 min-h-[1.25rem] truncate text-xs" title={file?.name}>
        {localError ? (
          <span className="text-red-400">{localError}</span>
        ) : file ? (
          <span className="text-slate-500">
            {file.name} &middot; {formatBytes(file.size)}
          </span>
        ) : null}
      </p>
    </div>
  );
}
