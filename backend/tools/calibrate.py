"""Pick a decision threshold from your own signature photos.

The bundle's threshold (0.3938) was chosen on scanned research datasets. Your
photos are phone pictures of paper, so the distance distributions differ - this
script measures them on your data and recommends an operating point.

Layout: one directory per person, holding that person's genuine signatures.
Files whose name starts with the forgery prefix (default "forg") count as
skilled forgeries of that person.

    data/
      ankit/        sig1.jpg sig2.jpg ...        (genuine)
                    forg_01.jpg                  (optional skilled forgeries)
      sneha/        sig1.jpg ...

Pairs built from that:
  genuine   - two signatures of the same person
  impostor  - a different person's signature (and any skilled forgeries)

Run from backend/ with the venv active:

    python -m tools.calibrate --data ../data --out ../calibration

It prints a threshold table, writes a histogram and a QC contact sheet of what
the model saw, and emits the environment variables to set.
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.cropping import canonicalize  # noqa: E402
from app.model_service import verifier  # noqa: E402

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")


def load_people(data_dir: Path, forgery_prefix: str, limit: int | None):
    """-> {person: {"genuine": [paths], "forgeries": [paths]}}"""
    people: dict[str, dict[str, list[Path]]] = {}
    for person_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        files = [
            f
            for f in sorted(person_dir.rglob("*"))
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        ]
        genuine = [f for f in files if not f.name.lower().startswith(forgery_prefix)]
        forgeries = [f for f in files if f.name.lower().startswith(forgery_prefix)]
        if limit:
            genuine, forgeries = genuine[:limit], forgeries[:limit]
        if len(genuine) >= 2:
            people[person_dir.name] = {"genuine": genuine, "forgeries": forgeries}
        elif genuine:
            print(f"  skipping {person_dir.name}: needs at least 2 genuine signatures")
    return people


def embed_images(paths: list[Path], crop_mode: str, variants: int) -> tuple[torch.Tensor, list[np.ndarray]]:
    """Run the production path on each image. Returns (embeddings, previews)."""
    margins = verifier.tta_margins() if variants > 1 else [0.10]
    embeddings, previews = [], []
    for i, path in enumerate(paths, 1):
        data = np.fromfile(str(path), dtype=np.uint8)  # handles non-ASCII paths
        bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if bgr is None:
            raise SystemExit(f"Could not read {path}")
        if crop_mode == "ink":
            arrs = [
                verifier._process(canonicalize(bgr, m), "reference", already_cropped=True)
                for m in margins
            ]
        else:  # "auto": full-photo localization, as when no box is drawn in the UI
            arrs = [verifier._process(bgr, "reference", already_cropped=False)]
        with torch.inference_mode():
            torch.set_flush_denormal(True)
            e = verifier._net.embed(torch.from_numpy(np.stack(arrs)[:, None]))
        embeddings.append(torch.nn.functional.normalize(e.mean(0, keepdim=True), dim=1)[0])
        previews.append(arrs[len(arrs) // 2])
        print(f"\r  {i}/{len(paths)} images", end="", flush=True)
    print()
    return torch.stack(embeddings), previews


def eer_point(genuine: np.ndarray, impostor: np.ndarray) -> tuple[float, float]:
    """Threshold where false-accept and false-reject rates meet."""
    ts = np.linspace(0, 2, 4001)
    frr = 1 - np.searchsorted(np.sort(genuine), ts, side="right") / len(genuine)
    far = np.searchsorted(np.sort(impostor), ts, side="right") / len(impostor)
    i = int(np.argmin(np.abs(frr - far)))
    return float(ts[i]), float((frr[i] + far[i]) / 2)


def threshold_for_far(impostor: np.ndarray, target: float) -> float:
    return float(np.percentile(impostor, target * 100))


def inconclusive_band(
    genuine: np.ndarray, impostor: np.ndarray, threshold: float,
    shell: float = 0.02, error_floor: float = 0.25, cap: float = 0.25,
) -> float:
    """How far from the threshold calls stay barely better than chance.

    Walks outward in thin shells and stops at the first one where the local
    error rate drops below `error_floor`; reporting the region inside as
    inconclusive is more honest than a green or red verdict. Uses local shells
    rather than the cumulative band, which would keep widening on overlapping
    data and swallow most of the range.
    """
    band = shell
    while band < cap:
        lo, hi = band, band + shell
        in_g = genuine[(np.abs(genuine - threshold) >= lo) & (np.abs(genuine - threshold) < hi)]
        in_i = impostor[(np.abs(impostor - threshold) >= lo) & (np.abs(impostor - threshold) < hi)]
        total = len(in_g) + len(in_i)
        if total >= 10:
            errors = (in_g > threshold).sum() + (in_i <= threshold).sum()
            if errors / total < error_floor:
                break
        band += shell
    return round(min(band, cap), 3)


def histogram_png(genuine: np.ndarray, impostor: np.ndarray, threshold: float, band: float, path: Path):
    W, H, pad = 900, 380, 45
    img = np.full((H, W, 3), 255, np.uint8)
    edges = np.linspace(0, max(1.2, float(max(genuine.max(), impostor.max())) * 1.05), 60)
    hg, _ = np.histogram(genuine, bins=edges)
    hi, _ = np.histogram(impostor, bins=edges)
    bw = (W - 2 * pad) / (len(edges) - 1)
    x_of = lambda v: pad + (v / edges[-1]) * (W - 2 * pad)

    b0, b1 = int(x_of(threshold - band)), int(x_of(threshold + band))
    cv2.rectangle(img, (b0, pad), (b1, H - pad), (200, 235, 255), -1)
    # Each distribution is scaled to its own peak: there are usually far more
    # impostor pairs than genuine ones, and a shared scale would flatten the
    # genuine curve into invisibility.
    for h, colour in ((hg, (90, 170, 60)), (hi, (60, 60, 210))):
        top = h.max() or 1
        for i, v in enumerate(h):
            x0 = int(pad + i * bw)
            y0 = int(H - pad - (v / top) * (H - 2 * pad))
            overlay = img.copy()
            cv2.rectangle(overlay, (x0, y0), (int(x0 + bw) - 1, H - pad), colour, -1)
            cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)
    cv2.line(img, (int(x_of(threshold)), pad), (int(x_of(threshold)), H - pad), (0, 0, 0), 2)
    cv2.putText(img, f"threshold {threshold:.3f}", (int(x_of(threshold)) + 6, pad + 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(img, "genuine", (pad, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (90, 170, 60), 2)
    cv2.putText(img, "impostor", (pad + 110, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 60, 210), 2)
    cv2.putText(img, "inconclusive band", (pad + 240, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (170, 140, 60), 2)
    cv2.putText(img, "(each curve scaled to its own peak)", (pad + 470, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 120), 1)
    for v in np.linspace(0, edges[-1], 7):
        cv2.putText(img, f"{v:.2f}", (int(x_of(v)) - 14, H - pad + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 80, 80), 1)
    cv2.imwrite(str(path), img)


def contact_sheet(previews: list[np.ndarray], labels: list[str], path: Path):
    """What the model saw for every input - check this before trusting the numbers."""
    tile, pad, cols = 155, 22, 8
    rows = (len(previews) + cols - 1) // cols
    sheet = np.full((rows * (tile + pad), cols * (tile + 6)), 255, np.uint8)
    for i, (arr, label) in enumerate(zip(previews, labels)):
        r, c = divmod(i, cols)
        y, x = r * (tile + pad), c * (tile + 6)
        sheet[y + pad : y + pad + tile, x : x + tile] = (arr * 255).astype(np.uint8)
        cv2.putText(sheet, label[:22], (x + 2, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.38, 0, 1)
    cv2.imwrite(str(path), sheet)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, type=Path, help="Directory of per-person folders.")
    ap.add_argument("--out", type=Path, default=Path("calibration"), help="Where to write the report.")
    ap.add_argument("--forgery-prefix", default="forg", help='Filename prefix marking skilled forgeries.')
    ap.add_argument("--limit", type=int, default=None, help="Max images per person.")
    ap.add_argument("--crop-mode", choices=("ink", "auto"), default="ink",
                    help="ink: tighten to the strokes (images should be roughly cropped already). "
                         "auto: full-photo localization, as when no box is drawn.")
    ap.add_argument("--variants", type=int, default=config.TTA_VARIANTS, help="Crop margins averaged per image.")
    ap.add_argument("--target-far", type=float, default=0.05, help="False-accept rate for one recommendation.")
    args = ap.parse_args()

    if not args.data.is_dir():
        raise SystemExit(f"No such directory: {args.data}")
    args.out.mkdir(parents=True, exist_ok=True)

    verifier.load()
    print(f"Model loaded. Bundle threshold {verifier.threshold:.4f}\n")

    people = load_people(args.data, args.forgery_prefix.lower(), args.limit)
    if len(people) < 2:
        raise SystemExit(
            "Need at least 2 people (impostor pairs come from different people), "
            f"found {len(people)} in {args.data}."
        )
    counts = ", ".join(f"{k}: {len(v['genuine'])}g+{len(v['forgeries'])}f" for k, v in people.items())
    print(f"{len(people)} people ({counts})")

    all_paths, all_labels, owner, is_forgery = [], [], [], []
    for person, sets in people.items():
        for kind in ("genuine", "forgeries"):
            for p in sets[kind]:
                all_paths.append(p); all_labels.append(f"{person}/{p.name}")
                owner.append(person); is_forgery.append(kind == "forgeries")

    print(f"Embedding {len(all_paths)} images ({args.crop_mode} crop, {args.variants} variants)")
    emb, previews = embed_images(all_paths, args.crop_mode, args.variants)
    owner = np.array(owner); is_forgery = np.array(is_forgery)

    dist = torch.cdist(emb, emb).numpy()
    genuine, impostor, rows = [], [], []
    for i, j in itertools.combinations(range(len(all_paths)), 2):
        d = float(dist[i, j])
        same = owner[i] == owner[j]
        if same and not is_forgery[i] and not is_forgery[j]:
            kind = "genuine"; genuine.append(d)
        elif same:  # one side is a skilled forgery of this person
            if is_forgery[i] and is_forgery[j]:
                continue  # forgery vs forgery says nothing
            kind = "forgery"; impostor.append(d)
        else:
            if is_forgery[i] or is_forgery[j]:
                continue  # another person's forgery is a muddle; skip
            kind = "different-person"; impostor.append(d)
        rows.append([all_labels[i], all_labels[j], kind, f"{d:.6f}", i, j])

    genuine, impostor = np.array(genuine), np.array(impostor)
    if not len(genuine) or not len(impostor):
        raise SystemExit("Not enough pairs: need genuine pairs and impostor pairs.")
    print(f"\n{len(genuine)} genuine pairs, {len(impostor)} impostor pairs")
    print(f"  genuine  median={np.median(genuine):.3f}  p90={np.percentile(genuine, 90):.3f}")
    print(f"  impostor median={np.median(impostor):.3f}  p10={np.percentile(impostor, 10):.3f}")

    # Balanced accuracy, not raw accuracy: impostor pairs usually outnumber
    # genuine ones by a lot, so raw accuracy mostly reports the impostor side.
    print(f"\n{'threshold':>10} {'false accept':>13} {'false reject':>13} {'balanced acc':>13}")
    bundle = verifier.threshold
    eer_t, eer_v = eer_point(genuine, impostor)
    far_t = threshold_for_far(impostor, args.target_far)
    candidates = sorted({round(t, 3) for t in list(np.arange(0.10, 0.85, 0.05)) + [bundle, eer_t, far_t]})
    for t in candidates:
        far = float((impostor <= t).mean()); frr = float((genuine > t).mean())
        acc = ((1 - far) + (1 - frr)) / 2
        tags = []
        if abs(t - round(bundle, 3)) < 1e-9: tags.append("bundle")
        if abs(t - round(eer_t, 3)) < 1e-9: tags.append("EER")
        if abs(t - round(far_t, 3)) < 1e-9: tags.append(f"FAR={args.target_far:.0%}")
        print(f"{t:>10.3f} {far:>12.1%} {frr:>13.1%} {acc:>9.1%}  {' '.join(tags)}")

    band = inconclusive_band(genuine, impostor, eer_t)
    print(f"\nEER {eer_v:.1%} at threshold {eer_t:.3f}")
    print(f"Recommended: THRESHOLD_OVERRIDE={eer_t:.4f}  BORDERLINE_BAND={band:.3f}")
    print(f"  (at that threshold: false accept {float((impostor <= eer_t).mean()):.1%}, "
          f"false reject {float((genuine > eer_t).mean()):.1%}; "
          f"{float(np.mean(np.abs(np.concatenate([genuine, impostor]) - eer_t) < band)):.0%} of pairs "
          "would be reported inconclusive)")

    # Which images are involved in the most wrong calls? A single bad photo -
    # poor crop, bad lighting - can drag down every comparison it appears in,
    # and looks like "the app broke" when you hit it mid-session.
    wrong_per_image: dict[str, list[int]] = {label: [0, 0] for label in all_labels}
    csv_rows = []
    for label_a, label_b, kind, dstr, i, j in rows:
        d = float(dstr)
        called_genuine = d <= eer_t
        correct = called_genuine == (kind == "genuine")
        for label in (label_a, label_b):
            wrong_per_image[label][1] += 1
            if not correct:
                wrong_per_image[label][0] += 1
        csv_rows.append([label_a, label_b, kind, dstr,
                         "genuine" if called_genuine else "different",
                         "ok" if correct else "WRONG"])

    ranked = sorted(
        ((lbl, w, n) for lbl, (w, n) in wrong_per_image.items() if n),
        key=lambda t: (-t[1] / t[2], -t[1]),
    )
    if ranked and ranked[0][1]:
        print(f"\nimages involved in the most wrong calls (at threshold {eer_t:.3f}):")
        for lbl, w, n in ranked[:8]:
            if not w:
                break
            print(f"  {w:3d}/{n:3d} wrong  {lbl}")
        print("  A photo far above the others is worth re-checking in "
              "what_the_model_saw.png, or re-shooting.")

    (args.out / "pairs.csv").write_text(
        "image_a,image_b,kind,distance,called,result\n"
        + "\n".join(",".join(r) for r in csv_rows), encoding="utf-8")
    (args.out / "calibration.json").write_text(json.dumps({
        "bundle_threshold": round(bundle, 6),
        "recommended_threshold": round(eer_t, 6),
        "recommended_band": band,
        "eer": round(eer_v, 6),
        "threshold_at_target_far": round(far_t, 6),
        "target_far": args.target_far,
        "crop_mode": args.crop_mode,
        "variants": args.variants,
        "people": {k: len(v["genuine"]) for k, v in people.items()},
        "n_genuine_pairs": len(genuine),
        "n_impostor_pairs": len(impostor),
    }, indent=2), encoding="utf-8")
    histogram_png(genuine, impostor, eer_t, band, args.out / "distances.png")
    contact_sheet(previews, all_labels, args.out / "what_the_model_saw.png")

    print(f"\nWrote {args.out}/pairs.csv, calibration.json, distances.png, what_the_model_saw.png")
    print("Check what_the_model_saw.png before trusting any of this: if an image shows "
          "paper edges or fingers instead of strokes, remove or re-crop it and re-run.")
    print(f"\nTo use the recommended values, start the backend with:\n"
          f'  set THRESHOLD_OVERRIDE={eer_t:.4f} && set BORDERLINE_BAND={band:.3f} && '
          f"uvicorn app.main:app --port 8000")


if __name__ == "__main__":
    main()
