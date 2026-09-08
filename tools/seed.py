"""
One-time bootstrap: turn the legacy Skins.java enum into this repository.

For every enum constant it recovers the source PNG by decoding the base64 texture
property to its textures.minecraft.net URL and downloading it, then writes
manifest.json carrying the *existing* texture and signature verbatim.

Nothing is uploaded to MineSkin. The signatures already in the enum stay valid
indefinitely, so re-uploading would regenerate all 499 for no reason and throw
away the provenance of skins that have worked for years.

    python tools/seed.py --plugin ../minescape.me
"""

import argparse
import base64
import hashlib
import json
import shutil
import struct
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import skins_source

SKIN_PACKAGE = "modules/minescape-npc/src/main/java/me/minescape/newo/entity/skin"
USER_AGENT = "MineScapeSkinSeeder/1.0 (+https://github.com/AshleyThew/minescape-skins)"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def texture_url(texture):
    """Decodes a Mojang texture property value to its skin URL."""
    payload = json.loads(base64.b64decode(texture))
    url = payload["textures"]["SKIN"]["url"]
    # Mojang still emits http:// in these blobs; the CDN serves https fine.
    return url.replace("http://", "https://", 1)


def download(url, attempts=4):
    last = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError("could not download " + url + ": " + str(last))


def png_size(data):
    """(width, height) from the IHDR chunk, or None if this is not a PNG."""
    if not data.startswith(PNG_MAGIC):
        return None
    return struct.unpack(">II", data[16:24])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin", required=True, help="path to the minescape.me checkout")
    ap.add_argument("--out", default=".", help="repository root to write into")
    args = ap.parse_args()

    skin_dir = Path(args.plugin) / SKIN_PACKAGE
    if not (skin_dir / "Skins.java").exists():
        sys.exit("no Skins.java under " + str(skin_dir))

    root = Path(args.out)
    skins_out = root / "skins"
    if skins_out.exists():
        shutil.rmtree(skins_out)
    skins_out.mkdir(parents=True)

    entries = skins_source.parse(skin_dir)
    print("parsed " + str(len(entries)) + " constants from Skins.java")

    # 17 texture hashes are shared by two or three names, so cache by URL and write
    # a copy per name - every enum name owns its own file.
    by_url = {}
    manifest = {}
    failures = []

    for i, (name, texture, signature, display) in enumerate(entries, 1):
        try:
            url = texture_url(texture)
        except Exception as e:
            failures.append((name, "undecodable texture: " + str(e)))
            continue

        if url not in by_url:
            data = download(url)
            size = png_size(data)
            if size is None:
                failures.append((name, "downloaded bytes are not a PNG"))
                continue
            if size not in ((64, 64), (64, 32)):
                failures.append((name, "unexpected dimensions " + str(size)))
                continue
            by_url[url] = data
            print("  [" + str(i) + "/" + str(len(entries)) + "] " + name + " " + str(size[0]) + "x" + str(size[1]) + " " + str(len(data)) + "b")
        else:
            print("  [" + str(i) + "/" + str(len(entries)) + "] " + name + " (shared texture)")

        data = by_url[url]
        (skins_out / (name + ".png")).write_bytes(data)

        entry = {
            "texture": texture,
            "signature": signature,
            "image_sha256": hashlib.sha256(data).hexdigest(),
            "texture_url": url,
        }
        if display:
            entry["display"] = display
        manifest[name] = entry

    if failures:
        for name, why in failures:
            print("FAILED " + name + ": " + why, file=sys.stderr)
        sys.exit(str(len(failures)) + " skins could not be seeded - refusing to write a partial manifest")

    doc = {
        "version": 1,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": None,
        "count": len(manifest),
        "skins": dict(sorted(manifest.items())),
    }
    (root / "manifest.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("")
    print("wrote " + str(len(manifest)) + " PNGs to " + str(skins_out))
    print("wrote manifest.json (" + str(len(by_url)) + " unique textures)")


if __name__ == "__main__":
    main()
