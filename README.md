---
title: Glyph
emoji: ✍️
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Glyph — Signature Verification

Glyph compares a test signature against a known-genuine reference: a Python
**FastAPI** backend that owns the model and the OpenCV/scikit-image
preprocessing pipeline, and a **Next.js** frontend for uploading the two images
and inspecting the result.

> The block above is Hugging Face Space configuration. It has to sit at the top
> of the README in the Space repo, and GitHub renders it as a table — harmless.

> **Research prototype — use as a decision-support signal alongside expert
> review, not a sole determinant.**

---

## Project layout

```
.
├── model/                          # model code + weights (loaded, never duplicated)
│   ├── signature_model_bundle.pt   # state dict + threshold / embed_dim / img_size
│   ├── model_architecture.py       # SigNetBackbone, SiameseSignatureNet
│   └── preprocessing.py            # SignaturePreprocessor
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, routes, error handlers
│   │   ├── model_service.py        # model loading, preprocessing, inference
│   │   ├── config.py               # env-var configuration
│   │   ├── errors.py               # typed errors -> clean JSON
│   │   └── schemas.py              # response models
│   ├── tools/
│   │   └── calibrate.py            # fit the threshold on your own photos
│   └── requirements.txt
├── frontend/
│   ├── app/                        # App Router pages
│   ├── components/                 # dropzone, result panel
│   └── lib/api.ts                  # typed client for the backend
├── Dockerfile                      # backend image for the Hugging Face Space
└── README.md
```

The backend **imports** `model_architecture.py` and `preprocessing.py` straight
out of `model/` rather than copying them, so inference always runs the exact
pipeline the model was trained against. Edit those files and restart the server
to pick up changes.

---

## 1. Backend (FastAPI, port 8000)

Requires Python 3.10+.

### Setup

```bash
cd backend
python -m venv .venv
```

Activate the virtualenv:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Windows Git Bash
source .venv/Scripts/activate
# macOS / Linux
source .venv/bin/activate
```

Install dependencies. CPU-only torch is much smaller and plenty fast for
single-pair inference:

```bash
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

> **NumPy 2 note:** `opencv-python` below 4.10 is compiled against NumPy 1.x and
> dies on import with `_ARRAY_API not found` when NumPy 2 is installed.
> `requirements.txt` pins `opencv-python>=4.10` to keep the two in step — worth
> remembering if you ever install into an existing environment.

### Run

```bash
# from backend/
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

On startup the server loads the bundle and logs the threshold it will use.
Interactive API docs: <http://localhost:8000/docs>.

If the model fails to load, the server **stays up** and reports the reason at
`/api/health` — easier to debug than a process that exits instantly. `/api/verify`
then returns `503` until it is fixed.

### Endpoints

#### `GET /api/health`

```json
{
  "status": "ok",
  "model_loaded": true,
  "threshold": 0.393784,
  "img_size": 155,
  "embed_dim": 128,
  "model_info": { "architecture": "SigNetBackbone-GAP", "val_eer": 0.2317, "...": "..." }
}
```

#### `POST /api/verify`

`multipart/form-data` with two file fields, `reference` and `test`, plus two
optional crop fields, `reference_crop` and `test_crop`.

```bash
curl -X POST http://localhost:8000/api/verify \
  -F "reference=@/path/to/reference.png" \
  -F "test=@/path/to/test.png" \
  -F 'test_crop={"x":0.2,"y":0.33,"width":0.6,"height":0.2}'
```

A crop is JSON in `0–1` units of the EXIF-oriented image. How it changes the
pipeline:

| | Without a crop | With a crop |
| --- | --- | --- |
| Localization | Automatic (`already_cropped=False`) | Skipped (`already_cropped=True`) |
| Before `process()` | — | Box cut at full resolution, then re-tightened to the ink with a fixed 10% margin and resized to 350 px |

The re-tightening step is there because the pipeline is sensitive to the size
of the image it gets: both the 350 px downsample factor and the Hough deskew's
`minLineLength` scale with it. Without that step, differently drawn boxes around
the same signature rotated it differently, and the verdict flipped. With it, the
box mostly just has to leave out clutter. Measured on 110 CEDAR signatures with
5 random boxes each (2–40% margin per side):

| | Box used as drawn | Re-tightened |
| --- | --- | --- |
| Median distance between crops of the same signature | 0.093 | 0.001 |
| Signatures where box choice alone crosses the threshold | 23/110 | 3/110 |

The remaining sensitivity comes from the Hough deskew inside `preprocessing.py`,
which picks noticeably different angles for tiny pixel differences. Replacing it
at inference is not an option: on CEDAR, `minAreaRect`-only deskew raised EER
from 0.202 to 0.231, and no deskew raised it to 0.232, because the model was
trained on the Hough-deskewed images. A stable deskew needs a retrain.

### Averaging over crop margins

Because of that deskew, a single crop still made repeat comparisons jumpy: with
a box redrawn by hand, the same genuine pair could come back authentic twice and
forged once. So when a crop is supplied, the backend renders it at
`TTA_VARIANTS` margins around the ink (7 by default, 0.03 apart), embeds all of
them in one batch, and compares the **mean embedding** of each side. The margins
are fixed, not random, so results stay reproducible.

Measured on 55 CEDAR genuine pairs, each re-cropped by hand 5 times:

| Variants averaged | Run-to-run spread (p90) | Pairs whose verdict flips between runs |
| --- | --- | --- |
| 1 | 0.197 | 9/55 |
| 3 | 0.088 | 3/55 |
| 5 | 0.079 | 3/55 |
| 7 (default) | 0.055 | 1/55 |

`variant_spread` in the response is the max-minus-min distance across those
variants: a large value means this particular pair is very sensitive to where
the crop falls, and the previews are worth a careful look.

### "Too close to call"

Averaging cannot rescue a pair that genuinely sits on the boundary. Of the 55
genuine pairs, 8 sat within 0.05 of the threshold and 5 of those flipped between
hand-redrawn crops. So a distance within `BORDERLINE_BAND` (0.05) of the
threshold is returned with `is_borderline: true`, and the UI shows an amber
**TOO CLOSE TO CALL** instead of a green or red verdict. `is_genuine` still
carries the raw `distance <= threshold` comparison, so existing callers are
unaffected.

#### `POST /api/preprocess`

Runs preprocessing only (no model) for one image and returns what the model
would see. The UI calls it while you adjust the crop.

Fields: `image` (file), `field` (`reference` / `test`, used in messages), and
an optional `crop`.

```json
{ "preprocessed_base64": "iVBORw0KGgo...", "ink_fraction": 0.0426, "signature_detected": true }
```

Unlike `/api/verify`, it returns the image even when no signature is found, so
you can see why.

```json
{
  "distance": 0.2841,
  "threshold": 0.393784,
  "max_distance": 2.0,
  "is_genuine": true,
  "is_borderline": false,
  "borderline_band": 0.05,
  "variants": 7,
  "variant_spread": 0.0413,
  "confidence": 0.2784,
  "preprocessed_ref_base64": "iVBORw0KGgo...",
  "preprocessed_test_base64": "iVBORw0KGgo..."
}
```

The two base64 fields are raw PNG payloads **without** a `data:` prefix — the
frontend prepends `data:image/png;base64,`.

#### Errors

Every expected failure returns the same shape, never a stack trace:

```json
{
  "error": {
    "code": "no_signature_detected",
    "message": "No signature strokes were found in the test image.",
    "field": "test",
    "hint": "Crop closer to the signature, or use a photo with stronger contrast..."
  }
}
```

| Code | Status | Cause |
| --- | --- | --- |
| `image_decode_failed` | 415 | Not an image, corrupt, or far too small |
| `image_too_large` | 413 | Over the upload / pixel limit |
| `no_signature_detected` | 422 | Preprocessing produced a near-empty canvas |
| `preprocessing_failed` | 422 | The OpenCV pipeline raised on this image |
| `model_not_loaded` | 503 | Bundle failed to load — see `/api/health` |
| `internal_error` | 500 | Unexpected; traceback is in the server log |

`field` names the offending upload (`reference` / `test`) so the UI can
highlight the right box.

### Configuration (environment variables)

| Variable | Default | Purpose |
| --- | --- | --- |
| `MODEL_DIR` | `../model` | Directory holding the model files |
| `MODEL_BUNDLE` | `$MODEL_DIR/signature_model_bundle.pt` | Explicit bundle path |
| `MAX_UPLOAD_BYTES` | `15728640` (15 MB) | Per-file upload cap |
| `MAX_IMAGE_PIXELS` | `50000000` | Decompression-bomb ceiling |
| `MIN_INK_FRACTION` | `0.004` | Minimum ink in the 155×155 output before we call it "no signature" |
| `TTA_VARIANTS` | `7` | Crop margins averaged per image when a crop is given; `1` disables |
| `TTA_MARGIN_STEP` | `0.03` | Spacing between those margins |
| `BORDERLINE_BAND` | `0.05` | Distances this close to the threshold are reported inconclusive |
| `THRESHOLD_OVERRIDE` | unset | Threshold fitted on your own data; replaces the bundle's (see Calibrating) |
| `CORS_ORIGIN_REGEX` | unset | Regex of allowed origins, for Vercel preview URLs |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowed origins |
| `TORCH_NUM_THREADS` | `4` | Torch intra-op threads |

---

## 2. Frontend (Next.js, port 3000)

Requires Node.js 18.18+ (20+ recommended).

```bash
cd frontend
npm install
cp .env.local.example .env.local   # already created for you if missing
npm run dev
```

Open <http://localhost:3000>.

The frontend calls the backend **directly** using `NEXT_PUBLIC_API_URL`
(default `http://localhost:8000`); the backend's CORS config already allows
`localhost:3000`. To point at a backend elsewhere, edit `.env.local`:

```
NEXT_PUBLIC_API_URL=http://192.168.1.50:8000
```

and add that origin to the backend's `CORS_ORIGINS`. `NEXT_PUBLIC_*` variables
are inlined at build time — restart `npm run dev` after changing it.

### What the UI shows

- Two drag-and-drop (or click-to-browse) uploads. Once a photo is loaded you can
  drag a box around the signature (optional), and a **live preview of the
  model's input** updates as you adjust it.
- A live backend status line in the header, so a server that is down or a model
  that failed to load is obvious before you upload anything.
- The verdict — **LIKELY AUTHENTIC** (green), **LIKELY FORGED** (red), or
  **TOO CLOSE TO CALL** (amber) — with distance, threshold, margin and crop
  sensitivity.
- The distance plotted on its true `0 … 2.0` scale with the threshold marked.
- **The two preprocessed 155×155 images the model actually received**, so you can
  tell a genuine mismatch from a preprocessing failure (wrong crop, missing
  strokes, speckle). This is the single most useful debugging view in the app.

---

## 3. Running both together

Two terminals, both must be running:

| Terminal | Directory | Command |
| --- | --- | --- |
| 1 — backend | `backend/` | `uvicorn app.main:app --port 8000 --reload` |
| 2 — frontend | `frontend/` | `npm run dev` |

Then browse to <http://localhost:3000>. If the header shows *"backend
unreachable"*, terminal 1 is not running (or is on a different port than
`NEXT_PUBLIC_API_URL`).

---

## 4. Deploying (Vercel + Hugging Face)

The frontend goes to Vercel, the backend to a Hugging Face Space running the
`Dockerfile` in this repo. They are wired together by two settings: the
frontend's `NEXT_PUBLIC_API_URL` and the backend's CORS origins.

### Backend → Hugging Face Space

1. Create a Space: **SDK = Docker**, blank template. Its Git URL looks like
   `https://huggingface.co/spaces/<user>/glyph`.
2. Push this repo to it. The model bundle is tracked with Git LFS (it is over
   the 10 MB plain-file limit), so LFS must be installed:

   ```bash
   git lfs install
   git remote add space https://huggingface.co/spaces/<user>/glyph
   git push space main
   ```

3. In **Settings → Variables and secrets**, set:

   | Variable | Value |
   | --- | --- |
   | `CORS_ORIGINS` | `https://<your-app>.vercel.app` |
   | `CORS_ORIGIN_REGEX` | `https://<your-app>-.*\.vercel\.app` (optional, allows Vercel preview builds) |
   | `TTA_VARIANTS` | `5` on the free 2-vCPU tier, to keep a verify near ~2 s |

The Space serves on port 7860; check `https://<user>-glyph.hf.space/api/health`.
Free Spaces sleep when idle, so the first request after a nap pays a cold start
(container boot plus a few seconds of model loading) — worth warning testers
about, since it looks like a hang.

### Frontend → Vercel

1. Import the GitHub repo. Set **Root Directory** to `frontend` (this is a
   project setting; Vercel otherwise tries to build the repo root).
   Framework preset: Next.js. The rest of the defaults are correct.
2. Add an environment variable:

   | Variable | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_URL` | `https://<user>-glyph.hf.space` |

`NEXT_PUBLIC_*` is inlined at build time, so changing it needs a redeploy, not
just a restart.

### Before handing it to testers

- Open the deployed page and confirm the header says **model ready** with a
  green dot. "backend unreachable" means the Space is asleep, still building, or
  the CORS origins don't match.
- Both uploads and the previews cross the public internet on every crop change,
  and the photos are several MB each. On a slow connection this is the dominant
  cost, not inference.
- The Space is public by default, which means anyone with the URL can upload to
  it. If testers will use real signatures, make the Space private (Settings →
  Change visibility) and ask them to sign in, or keep it to sample signatures.

## How the verdict is computed

1. Each upload is decoded to BGR (EXIF rotation honoured — phone photos are
   frequently rotated) and passed to
   `SignaturePreprocessor.process(img, already_cropped=False)`, which locates the
   document and the signature region, then applies CLAHE, Sauvola binarization,
   blob filtering, deskew, stroke normalization, and crop-and-pad to 155×155.
2. The resulting `float32` array in `[0,1]` gets batch and channel dimensions —
   final shape `(2, 1, 155, 155)` for the pair — and goes through
   `model.embed()`, producing L2-normalized 128-d embeddings.
   Both images travel in **one** batched forward pass, which is safe only because
   the network is in `eval()` mode and its BatchNorm layers use running
   statistics rather than batch statistics.
3. `distance = F.pairwise_distance(e1, e2, p=2)`; `is_genuine = distance <= threshold`
   using the threshold stored in the bundle (`0.3938`).

### On `confidence`

`confidence` is a **margin, not a calibrated probability**. It reports how far
the distance sits from the decision boundary, scaled to `[0,1]`:

- genuine verdict: `(threshold - distance) / threshold`
- forged verdict: `(distance - threshold) / (2.0 - threshold)`

`2.0` is the largest possible Euclidean distance between two L2-normalized
vectors. A value near `0` means the pair landed essentially *on* the boundary and
the verdict could flip with a slightly different crop — treat those as
inconclusive. Do not read "87% confidence" as "87% likely to be genuine"; a
properly calibrated probability would require a held-out score distribution
fitted for that purpose.

## Calibrating the threshold on your own photos

The bundle's threshold (0.3938) was fitted on scanned research datasets. Your
photos are phone pictures of paper, so the distance distributions differ.
`backend/tools/calibrate.py` measures them on your data and recommends an
operating point.

Arrange your signatures one directory per person. Files whose name starts with
the forgery prefix (`forg` by default) count as skilled forgeries of that
person; everything else is genuine:

```
data/
  ankit/   sig1.jpg sig2.jpg sig3.jpg      forg_01.jpg   (forgeries optional)
  sneha/   sig1.jpg sig2.jpg ...
```

You need **at least two people** (impostor pairs come from different people) and
**at least two genuine signatures each**. Roughly crop each photo to the
signature area when you save it - the script tightens to the strokes from there,
and uncropped clutter produces garbage input, just as it does in the app.

```bash
cd backend
python -m tools.calibrate --data ../data --out ../calibration
```

It runs the exact production path (ink re-tightening, the same margin variants),
builds every genuine and impostor pair, and prints a threshold table:

```
 threshold  false accept  false reject  balanced acc
     0.250         4.3%         49.3%     73.2%
     0.394        15.2%         18.7%     83.0%  bundle
     0.416        17.4%         17.3%     82.6%  EER
```

Outputs in `--out`:

| File | What it is |
| --- | --- |
| `what_the_model_saw.png` | **Check this first.** Every input as the model saw it; if one shows paper edges or fingers, re-crop or drop it and re-run |
| `distances.png` | The two distance distributions with the threshold and inconclusive band |
| `pairs.csv` | Every pair: distance, what it was called, and `ok`/`WRONG` |
| `calibration.json` | The recommended values, machine-readable |

Then start the backend with the values it prints:

```powershell
$env:THRESHOLD_OVERRIDE="0.4160"; $env:BORDERLINE_BAND="0.040"; uvicorn app.main:app --port 8000
```

The header in the UI shows which threshold is live, tagged **calibrated** or
**bundle default**, and `/api/health` reports both.

It also ranks the images involved in the most wrong calls:

```
images involved in the most wrong calls (at threshold 0.416):
   13/ 31 wrong  writer5/original_5_2.png
   12/ 31 wrong  writer1/original_1_6.png
```

One photo far above the rest usually means a bad capture (poor crop, glare, weak
contrast) rather than a bad signature, and it drags down every comparison it
takes part in. Check it in `what_the_model_saw.png` and re-shoot it.

A few cautions worth keeping in mind:

- The recommended threshold is the EER point, which weights false accepts and
  false rejects equally. If wrongly accepting a forgery is worse than wrongly
  rejecting a genuine signature - usually true - take the stricter threshold
  from the `FAR=5%` row instead, and accept the higher rejection rate.
- Calibrate on data you are not also using to judge the result, and use enough
  of it. A handful of signatures from two people will produce a confident-looking
  number that does not generalise.
- Recalibrating moves the operating point along the same curve; it does not make
  the model better. Read the next section for what it can and cannot fix.

## Accuracy expectations

From the bundle's own metadata:

| Metric | Value |
| --- | --- |
| Validation EER | 0.232 |
| Validation accuracy | 0.768 |
| Test EER (English) | 0.168 |
| Test EER (mixed) | 0.233 |

An equal error rate around **0.17–0.23** means roughly one in five comparisons is
wrong at the chosen operating point — in both directions (genuine signatures
flagged as forged, and forgeries passed as genuine). That is a useful triage
signal and nothing more, which is exactly why the disclaimer is on the page.

Measured here on 55 CEDAR writers (95,040 pairs of signatures from *different
people* — the easiest case there is, two different names):

| | Median distance | At the bundle threshold |
| --- | --- | --- |
| Same writer | 0.240 | 23.3% wrongly rejected |
| Different people | 0.641 | **18.7% wrongly accepted** |

So about one in five comparisons between two unrelated people's signatures comes
back below the threshold, and another 9.6% lands in the inconclusive band. The
distributions overlap heavily: same-writer p90 (0.561) sits well above
different-people p10 (0.292). No threshold fixes this — holding false accepts to
5% needs a threshold of 0.222, which rejects 54% of genuine pairs.

Using several reference signatures per person helps the genuine side only: with
5 references and a mean embedding, false rejects fall from 25.5% to 13.9% while
false accepts stay near 18%.

Removing this ceiling means retraining — a metric-learning loss (triplet or
ArcFace) instead of plain contrastive, preserving the stroke-width information
the current pipeline skeletonizes away, a deskew that is stable under small crop
changes, and training on phone photos rather than scans.

Real-world photos are also harder than the training corpus: the preprocessing
pipeline was built for reasonably flat, reasonably lit documents. Always glance
at the preprocessed images before trusting a score.

### "It was fine for the first few comparisons, then it broke"

Worth knowing before you read too much into a testing session. At a ~20% error
rate, the chance that the first five comparisons all come out right is
0.8⁵ ≈ **33%** — so about one session in three looks flawless for four to six
trials and then appears to fall apart. Nothing is degrading: results are
reproducible, and identical inputs always produce an identical distance (the
service keeps no state between requests). You are simply accumulating draws from
a 1-in-5 error rate.

If a session feels wrong, run `tools/calibrate.py` over those images instead of
judging them one at a time. It compares every pair at once, so ordering cannot
matter, and `pairs.csv` plus the per-image ranking show whether the errors are
spread evenly (the model's normal rate) or concentrated in one bad photo.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `_ARRAY_API not found` on cv2 import | `pip install -U "opencv-python>=4.10"` — a NumPy 1.x build is installed under NumPy 2 |
| Header shows "backend unreachable" | Backend not running, or `NEXT_PUBLIC_API_URL` points elsewhere |
| Browser console shows a CORS error | Add the frontend origin to `CORS_ORIGINS` and restart uvicorn |
| `model_not_loaded` / 503 | Check `GET /api/health` for the load error and the uvicorn log |
| `no_signature_detected` on a valid photo | Crop closer, improve lighting/contrast, or lower `MIN_INK_FRACTION` |
| Preview shows stripes, a paper edge, or finger/shadow arcs | Automatic localization latched onto clutter (it picks the largest dark region). Drag a box around the signature |
| Same pair gives different distances on retries with different boxes | Should not happen with the ink re-tightening; if it does, check that nothing besides the signature is inside either box |
