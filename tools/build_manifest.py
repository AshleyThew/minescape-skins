"""
Rebuilds the skin manifest from the PNGs under skins/.

A skin is only sent to MineSkin when its PNG content actually changed - the image_sha256
recorded in the previous manifest is compared against the file on disk. Everything
unchanged is copied through byte-for-byte, so signatures that have worked for years are
never regenerated. Moving a skin between region folders is therefore free.

The manifest is not kept in git: main takes pull requests only and CI cannot commit to it,
so the published release is the store. --baseline points at the previous manifest (the
release asset) and --output at where to write the new one.

    python tools/build_manifest.py --check --baseline previous.json
    python tools/build_manifest.py --verify --baseline previous.json
    python tools/build_manifest.py --upload --baseline previous.json --output manifest.json
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
from skinfile import iter_skins

ROOT = Path(__file__).resolve().parent.parent
SKINS = ROOT / "skins"

# Replacing an existing skin throws away a texture and signature that were working, so a
# push that rewrites a big slice of the set is almost always a mistake and stops here.
#
# Adding new skins is not capped: a new name has no signature to destroy, and the repo is
# still being filled in batches of a hundred or more.
MAX_REPLACEMENTS = 50


def load_manifest(path):
    """The previous manifest's skins, or {} when there is none yet (the very first run)."""
    if path is None or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8")).get("skins", {})


def texture_url(texture):
    payload = json.loads(base64.b64decode(texture))
    return payload["textures"]["SKIN"]["url"].replace("http://", "https://", 1)


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    except Exception:
        return None


def current_skins():
    """name -> SkinFile for every PNG under skins/. Validation has already rejected duplicates."""
    return {f.name: f for f in iter_skins(SKINS) if f.path.suffix == ".png"}


def plan(files, previous, force_all):
    """Returns (changed, removed). A region move or a slim flip counts as changed only if it changes the image or the model."""
    changed = []
    for name, f in sorted(files.items()):
        if force_all:
            changed.append(name)
            continue
        entry = previous.get(name)
        if not entry:
            changed.append(name)
        elif entry.get("image_sha256") != hashlib.sha256(f.read()).hexdigest():
            changed.append(name)
        elif bool(entry.get("slim")) != f.slim:
            # The model is baked into the signed texture, so switching Steve/Alex needs a
            # fresh upload even though the image bytes are identical.
            changed.append(name)
    removed = sorted(set(previous) - set(files))
    return changed, removed


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="report changes, upload nothing")
    group.add_argument("--verify", action="store_true", help="like --check, but fail if anything is out of sync")
    group.add_argument("--upload", action="store_true", help="upload changed skins and rewrite the manifest")
    ap.add_argument("--force-all", action="store_true", help="re-upload every skin (rarely correct)")
    ap.add_argument("--baseline", type=Path, help="previous manifest to diff against (the release asset)")
    ap.add_argument("--output", type=Path, help="where to write the new manifest (--upload only)")
    args = ap.parse_args()

    errors = validator.validate(SKINS)
    if errors:
        for relpath, message in errors:
            print("ERROR " + relpath + ": " + message, file=sys.stderr)
        return 1

    files = current_skins()
    previous = load_manifest(args.baseline)
    if args.baseline and not Path(args.baseline).exists():
        print("no baseline manifest at " + str(args.baseline) + " - treating every skin as new")
    changed, removed = plan(files, previous, args.force_all)

    added = [n for n in changed if n not in previous]
    replaced = [n for n in changed if n in previous]

    print(str(len(files)) + " skins on disk, " + str(len(previous)) + " in the manifest")
    print(str(len(added)) + " new, " + str(len(replaced)) + " replaced, " + str(len(removed)) + " removed")
    for name in changed:
        print("  + " + name + "  (" + files[name].relpath + ")")
    for name in removed:
        print("  - " + name + "  (REMOVED - any NPC still using this name falls back to the default skin)")

    if args.check:
        return 0

    if args.verify:
        if changed or removed:
            print("")
            print("the published manifest does not match skins/ - merge to main to rebuild it.",
                  file=sys.stderr)
            return 1
        print("")
        print("the published manifest matches skins/")
        return 0

    if len(replaced) > MAX_REPLACEMENTS and not args.force_all:
        print("")
        print("refusing to replace " + str(len(replaced)) + " existing skins in one run (limit "
              + str(MAX_REPLACEMENTS) + ").", file=sys.stderr)
        print("each one discards a working texture and signature. Re-run with --force-all if "
              "this really is intended.", file=sys.stderr)
        return 1

    key = mineskin.api_key() if changed else None
    skins = {}

    for name, f in sorted(files.items()):
        digest = hashlib.sha256(f.read()).hexdigest()

        if name not in changed:
            entry = dict(previous[name])
            entry["image_sha256"] = digest
        else:
            print("uploading " + name + " (" + f.variant + ")...")
            value, signature = mineskin.upload(f.path, name, f.variant, key)
            entry = {
                "texture": value,
                "signature": signature,
                "image_sha256": digest,
                "texture_url": texture_url(value),
            }
            # A display override is content, not upload output - never lose it.
            if previous.get(name, {}).get("display"):
                entry["display"] = previous[name]["display"]
            if name != changed[-1]:
                time.sleep(mineskin.BETWEEN_SKINS)

        # Region and model are re-derived from the file every run, so moving or renaming a
        # file updates the manifest without costing an upload.
        entry["region"] = f.region
        if f.slim:
            entry["slim"] = True
        else:
            entry.pop("slim", None)
        skins[name] = entry

    skins = dict(sorted(skins.items()))

    # Writing an identical manifest with a fresh `generated` stamp would change its
    # SHA-256, which defeats the server's "same digest, nothing to download" shortcut.
    if skins == previous:
        print("")
        print("nothing changed - no new manifest written")
        return 0

    doc = {
        "version": 1,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": git_commit(),
        "count": len(skins),
        "skins": skins,
    }
    MANIFEST.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("")
    print("wrote manifest.json with " + str(len(skins)) + " skins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
