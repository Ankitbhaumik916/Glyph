"""Create the Hugging Face Space for Glyph's backend and set its variables.

Uses the HF HTTP API directly - no extra dependencies. Your token is read from
the environment and never printed.

    # Windows PowerShell
    $env:HF_TOKEN="hf_..."; python -m tools.deploy_space --space <user>/glyph

    # bash
    HF_TOKEN=hf_... python -m tools.deploy_space --space <user>/glyph

Create the token at https://huggingface.co/settings/tokens with **write**
access. Re-running is safe: an existing Space is left alone and variables are
overwritten with the values given here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://huggingface.co/api"


def call(method: str, path: str, token: str, payload: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode()
            try:
                return r.status, json.loads(body)
            except json.JSONDecodeError:
                return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body
    except urllib.error.URLError as e:
        raise SystemExit(f"Could not reach huggingface.co: {e.reason}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--space", required=True, help="Target Space, as <user-or-org>/<name>.")
    ap.add_argument("--vercel-url", default="", help="Vercel production URL, e.g. https://glyph.vercel.app")
    ap.add_argument("--vercel-regex", default=r"https://[a-z0-9-]+\.vercel\.app",
                    help="Regex of allowed origins; covers Vercel's per-deploy preview hostnames.")
    ap.add_argument("--tta-variants", default="5",
                    help="Crop margins averaged per image. 5 suits the free 2-vCPU tier; 7 is the local default.")
    ap.add_argument("--private", action="store_true",
                    help="Create the Space private. NOTE: a browser cannot call a private Space "
                         "without a token, so the Vercel frontend would need a server-side proxy.")
    ap.add_argument("--no-create", action="store_true", help="Only set variables on an existing Space.")
    ap.add_argument("--reviews-dataset", default="",
                    help="Private dataset repo for reviews, e.g. AnkBhau/glyph-reviews. "
                         "Also copies your token into the Space as a secret so it can write there.")
    ap.add_argument("--admin-key", default="",
                    help="Secret that unlocks /admin. Stored as a Space secret, not a variable.")
    args = ap.parse_args()

    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set HF_TOKEN first (https://huggingface.co/settings/tokens, write access).")
    if "/" not in args.space:
        raise SystemExit('--space must look like "<user>/glyph".')
    owner, name = args.space.split("/", 1)

    status, who = call("GET", "/whoami-v2", token)
    if status != 200:
        raise SystemExit(f"Token rejected by Hugging Face ({status}). Create a new write token.")
    print(f"Authenticated as {who.get('name')}")
    orgs = [o.get("name") for o in who.get("orgs", [])]
    if owner != who.get("name") and owner not in orgs:
        print(f"  warning: you are not {owner} and not in {orgs or 'any org'}; creation will likely fail")

    if not args.no_create:
        status, body = call("POST", "/repos/create", token, {
            "type": "space", "name": name, "organization": None if owner == who.get("name") else owner,
            "private": args.private, "sdk": "docker",
        })
        if status in (200, 201):
            print(f"Created Space {args.space} ({'private' if args.private else 'public'}, Docker SDK)")
        elif status == 409 or "already" in str(body).lower():
            print(f"Space {args.space} already exists - leaving it as is")
        else:
            raise SystemExit(f"Could not create the Space ({status}): {body}")

    variables = {
        "CORS_ORIGIN_REGEX": args.vercel_regex,
        "TTA_VARIANTS": args.tta_variants,
    }
    if args.vercel_url:
        variables["CORS_ORIGINS"] = args.vercel_url.rstrip("/")

    if args.reviews_dataset:
        variables["REVIEWS_DATASET"] = args.reviews_dataset

    for key, value in variables.items():
        status, body = call("POST", f"/spaces/{args.space}/variables", token,
                            {"key": key, "value": value})
        print(f"  {'set' if status in (200, 201) else f'FAILED ({status}) {body}'}: {key}={value}")

    # Secrets rather than variables: these are credentials, and the Space UI
    # keeps secrets write-only instead of displaying them back.
    secrets = {}
    if args.reviews_dataset:
        secrets["HF_TOKEN"] = token  # lets the Space write into the dataset repo
    if args.admin_key:
        secrets["ADMIN_KEY"] = args.admin_key
    for key, value in secrets.items():
        status, body = call("POST", f"/spaces/{args.space}/secrets", token,
                            {"key": key, "value": value})
        print(f"  {'set' if status in (200, 201) else f'FAILED ({status}) {body}'}: {key}=<hidden>")

    # Variable changes need a restart to take effect.
    status, _ = call("POST", f"/spaces/{args.space}/restart", token)
    print(f"  {'restart requested' if status in (200, 201, 204) else f'restart failed ({status})'}")

    # Space subdomains lowercase the id and replace anything that is not a
    # letter or digit with a dash: AnkBhau/Signet_bck -> ankbhau-signet-bck.
    slug = re.sub(r"[^a-z0-9]+", "-", f"{owner}-{name}".lower()).strip("-")
    print(f"\nSpace:     https://huggingface.co/spaces/{args.space}")
    print(f"Endpoint:  https://{slug}.hf.space")
    print("\nPush the code (run from the repo root):")
    print(f"  git remote add space https://huggingface.co/spaces/{args.space}")
    print("  git push space main          # asks for your HF username + token as the password")
    print("\nThen watch the build at the Space URL above; first build takes ~5-10 minutes.")
    if not args.vercel_url:
        print("\nOnce Vercel gives you a production URL, pin it exactly:")
        print(f"  python -m tools.deploy_space --space {args.space} --no-create "
              "--vercel-url https://<your-app>.vercel.app")


if __name__ == "__main__":
    main()
