"""Push just the backend to the Hugging Face Space.

Why not push the whole repo: the hero video has to be a plain file so Vercel can
serve it (Vercel does not fetch Git LFS objects), but Hugging Face rejects plain
.mp4 on push. The Space never needs the frontend - its Dockerfile only copies
backend/ and model/ - so this sends a single orphan commit containing only what
the image builds from, and the conflict disappears.

It also makes the push small: no frontend, no video, no history.

    cd backend
    $env:HF_TOKEN="hf_..."                       # bash: HF_TOKEN=hf_...
    python -m tools.push_space --space AnkBhau/Signet_bck
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Everything the Dockerfile needs, plus the Space's own config (README
# frontmatter) and .gitattributes so the model bundle still goes up as LFS.
INCLUDE = ["Dockerfile", ".dockerignore", ".gitattributes", "README.md", "backend", "model"]
BRANCH = "glyph-space-deploy"


def git(*args: str, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=str(ROOT)
    )
    if not quiet and result.stdout.strip():
        print(result.stdout.strip())
    if check and result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        raise SystemExit(f"git {' '.join(args)} failed")
    return result


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--space", required=True, help="Target Space, as <user>/<name>.")
    ap.add_argument("--message", default="Glyph backend", help="Commit message for the pushed snapshot.")
    args = ap.parse_args()

    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set HF_TOKEN first (a write token on the Space's account).")

    status = git("status", "--porcelain", quiet=True)
    if status.stdout.strip():
        raise SystemExit(
            "Working tree is not clean. Commit or stash first - this script switches branches."
        )

    original = git("rev-parse", "--abbrev-ref", "HEAD", quiet=True).stdout.strip()
    owner = args.space.split("/", 1)[0]
    url = f"https://{owner}:{token}@huggingface.co/spaces/{args.space}"

    print(f"Building a backend-only snapshot from {original}…")
    try:
        git("checkout", "--orphan", BRANCH, quiet=True)
        git("rm", "-r", "--cached", ".", "-q", quiet=True)
        git("add", *INCLUDE, quiet=True)
        git("-c", "user.name=glyph-deploy", "-c", "user.email=deploy@glyph.local",
            "commit", "-m", args.message, quiet=True)

        files = git("ls-files", quiet=True).stdout.splitlines()
        print(f"  {len(files)} files: " + ", ".join(sorted({f.split('/')[0] for f in files})))

        print(f"Pushing to {args.space}…")
        push = subprocess.run(
            ["git", "push", url, f"{BRANCH}:main", "--force"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        # Never echo the URL back: it carries the token.
        out = (push.stdout + push.stderr).replace(token, "***")
        print("\n".join(line for line in out.splitlines() if line.strip())[-1500:])
        if push.returncode != 0:
            raise SystemExit("Push failed.")
    finally:
        git("checkout", "-f", original, quiet=True)
        git("branch", "-D", BRANCH, check=False, quiet=True)

    print(f"\nDone. Watch the build at https://huggingface.co/spaces/{args.space}")


if __name__ == "__main__":
    main()
