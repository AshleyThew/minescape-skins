"""
Rebuilds manifest.json from the PNGs in skins/.

A skin is only sent to MineSkin when its PNG content actually changed - the
image_sha256 recorded in the manifest is compared against the file on disk.
Everything unchanged is copied through byte-for-byte, so signatures that have
worked for years are never regenerated.

    python tools/build_manifest.py --check     # report what would change, upload nothing
    python tools/build_manifest.py --upload    # upload changed skins and rewrite the manifest
"""

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import upload as mineskin
import validate as validator

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest.json"
SKINS = ROOT / "skins"

# A single push should never legitimately rewrite a big slice of the set. Above
# this, stop and make a human look - it is almost certainly a bulk mistake, and
# each upload costs quota and replaces a working signature.
MAX_UPLOADS = 50


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest():
    if not MANIFEST.exists():
        return {}
    return json.loads(MANIFEST.read_text(encoding="utf-8")).get("skins", {})


def texture_url(texture):
    payload = json.loads(base64.b64decode(texture))
    return payload["textures"]["SKIN"]["url"].replace("http://", "https://", 1)


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
    except Exception:
        return None


def plan(previous, force_all):
    """Returns (names_needing_upload, names_removed)."""
    current = sorted(p.stem for p in SKINS.glob("*.png"))
    changed = []
    for name in current:
        if force_all:
            changed.append(name)
            continue
        entry = previous.get(name)
        if not entry or entry.get("image_sha256") != sha256_file(SKINS / (name + ".png")):
            changed.append(name)
    removed = sorted(set(previous) - set(current))
    return current, changed, removed


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="report changes, upload nothing")
    group.add_argument("--upload", action="store_true", help="upload changed skins and rewrite the manifest")
    ap.add_argument("--force-all", action="store_true", help="re-upload every skin (rarely correct)")
    args = ap.parse_args()

    errors = validator.validate(SKINS)
    if errors:
        for e in errors:
            print("ERROR " + e, file=sys.stderr)
        return 1

    previous = load_manifest()
    current, changed, removed = plan(previous, args.force_all)

    print(str(len(current)) + " skins on disk, " + str(len(previous)) + " in the manifest")
    print(str(len(changed)) + " new or changed, " + str(len(removed)) + " removed")
    for name in changed:
        print("  + " + name)
    for name in removed:
        print("  - " + name)

    if args.check:
        return 0

    if len(changed) > MAX_UPLOADS and not args.force_all:
        print("")
        print("refusing to upload " + str(len(changed)) + " skins in one run (limit " + str(MAX_UPLOADS) + ").",
              file=sys.stderr)
        print("re-run with --force-all if this really is intended.", file=sys.stderr)
        return 1

    key = mineskin.api_key() if changed else None
    skins = {}

    for name in current:
        path = SKINS / (name + ".png")
        digest = sha256_file(path)

        if name not in changed:
            # Carry the existing entry through untouched, only refreshing the digest
            # field's companion data if the manifest predates it.
            entry = dict(previous[name])
            entry["image_sha256"] = digest
            skins[name] = entry
            continue

        print("uploading " + name + "...")
        value, signature = mineskin.upload(path, name, key)
        entry = {
            "texture": value,
            "signature": signature,
            "image_sha256": digest,
            "texture_url": texture_url(value),
        }
        # A display override is content, not upload output - never lose it.
        if previous.get(name, {}).get("display"):
            entry["display"] = previous[name]["display"]
        skins[name] = entry

        if name != changed[-1]:
            time.sleep(mineskin.BETWEEN_SKINS)

    doc = {
        "version": 1,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": git_commit(),
        "count": len(skins),
        "skins": dict(sorted(skins.items())),
    }
    MANIFEST.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("")
    print("wrote manifest.json with " + str(len(skins)) + " skins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
