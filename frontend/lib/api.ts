/**
 * Typed client for the FastAPI signature-verification backend.
 * The shapes here mirror backend/app/schemas.py.
 */

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export interface VerifyResult {
  distance: number;
  threshold: number;
  /** Largest possible distance between two L2-normalized embeddings (2.0). */
  max_distance: number;
  is_genuine: boolean;
  /** Distance is within borderline_band of the threshold: not reproducible, treat as inconclusive. */
  is_borderline: boolean;
  borderline_band: number;
  /** Crop margins averaged per image (1 when no crop was supplied). */
  variants: number;
  /** Max-min distance across per-variant comparisons: how crop-sensitive this pair is. */
  variant_spread: number;
  /** Margin from the decision boundary in [0,1] - not a calibrated probability. */
  confidence: number;
  /** Base64 PNG, no data: prefix. */
  preprocessed_ref_base64: string;
  preprocessed_test_base64: string;
  /** null when no crop box was drawn, or when the feature is switched off. */
  forensic?: ForensicAnalysis | null;
}

/** Crop rectangle in 0-1 units of the (EXIF-oriented) image. */
export interface CropBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PreviewResult {
  /** Base64 PNG, no data: prefix. */
  preprocessed_base64: string;
  ink_fraction: number;
  /** False when /api/verify would reject this image as having no signature. */
  signature_detected: boolean;
}

/** Supporting visual analysis. Explanatory only - never an input to the verdict. */
export interface ForensicAnalysis {
  scores: Record<string, number | null>;
  mean_score: number | null;
  measured: number;
  total: number;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  /** "reference" | "test" when one specific upload is at fault. */
  field?: string | null;
  hint?: string | null;
}

export interface HealthResult {
  status: string;
  model_loaded: boolean;
  threshold?: number | null;
  bundle_threshold?: number | null;
  /** "bundle" or "calibrated" when THRESHOLD_OVERRIDE is set. */
  threshold_source?: string | null;
  borderline_band?: number | null;
  img_size?: number | null;
  embed_dim?: number | null;
  model_info?: Record<string, unknown> | null;
  reviews_enabled?: boolean;
  error?: string | null;
}

export class ApiError extends Error {
  readonly detail: ApiErrorDetail;

  constructor(detail: ApiErrorDetail) {
    super(detail.message);
    this.name = "ApiError";
    this.detail = detail;
  }
}

/** Turn any failed response into an ApiError with a message worth showing. */
async function toApiError(response: Response): Promise<ApiError> {
  let detail: ApiErrorDetail = {
    code: `http_${response.status}`,
    message: `The server returned ${response.status} ${response.statusText}.`,
  };
  try {
    const body = await response.json();
    if (body?.error?.message) {
      detail = body.error as ApiErrorDetail;
    } else if (Array.isArray(body?.detail)) {
      // FastAPI's own request-validation shape (e.g. a missing file field).
      detail = {
        code: "invalid_request",
        message: body.detail.map((d: { msg: string }) => d.msg).join("; "),
      };
    } else if (typeof body?.detail === "string") {
      detail = { code: "invalid_request", message: body.detail };
    }
  } catch {
    // Non-JSON body (a proxy error page, say) - keep the status-based message.
  }
  return new ApiError(detail);
}

async function postForm(path: string, form: FormData, signal?: AbortSignal): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { method: "POST", body: form, signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError({
      code: "backend_unreachable",
      message: `Could not reach the backend at ${API_URL}.`,
      hint: "Make sure the FastAPI server is running (uvicorn app.main:app --port 8000).",
    });
  }

  if (!response.ok) throw await toApiError(response);
  return response;
}

export async function verifySignatures(
  reference: File,
  test: File,
  crops: { reference: CropBox | null; test: CropBox | null },
  signal?: AbortSignal,
): Promise<VerifyResult> {
  const form = new FormData();
  form.append("reference", reference);
  form.append("test", test);
  if (crops.reference) form.append("reference_crop", JSON.stringify(crops.reference));
  if (crops.test) form.append("test_crop", JSON.stringify(crops.test));
  const response = await postForm("/api/verify", form, signal);
  return (await response.json()) as VerifyResult;
}

/** Run preprocessing only, to show the model's input while the crop is adjusted. */
export async function previewSignature(
  image: File,
  field: "reference" | "test",
  crop: CropBox | null,
  signal?: AbortSignal,
): Promise<PreviewResult> {
  const form = new FormData();
  form.append("image", image);
  form.append("field", field);
  if (crop) form.append("crop", JSON.stringify(crop));
  const response = await postForm("/api/preprocess", form, signal);
  return (await response.json()) as PreviewResult;
}

export interface ReviewInput {
  rating: number;
  verdict_correct: "yes" | "no" | "unsure" | null;
  comment: string;
  name: string;
  distance?: number;
  threshold?: number;
  is_genuine?: boolean;
  is_borderline?: boolean;
  variant_spread?: number;
}

export interface ReviewRecord extends ReviewInput {
  id: string;
  submitted_at: string;
}

/** Anyone can leave a review; only the owner can read them back. */
export async function submitReview(review: ReviewInput, signal?: AbortSignal): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(review),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError({
      code: "backend_unreachable",
      message: `Could not reach the backend at ${API_URL}.`,
    });
  }
  if (!response.ok) throw await toApiError(response);
  return ((await response.json()) as { id: string }).id;
}

/** Owner-only: needs the admin key the server was started with. */
export async function fetchReviews(
  adminKey: string,
  signal?: AbortSignal,
): Promise<ReviewRecord[]> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/reviews`, {
      headers: { "X-Admin-Key": adminKey },
      cache: "no-store",
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError({
      code: "backend_unreachable",
      message: `Could not reach the backend at ${API_URL}.`,
    });
  }
  if (!response.ok) throw await toApiError(response);
  return ((await response.json()) as { reviews: ReviewRecord[] }).reviews;
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResult> {
  const response = await fetch(`${API_URL}/api/health`, { signal, cache: "no-store" });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as HealthResult;
}
