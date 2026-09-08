"""
Checks everything under skins/ before the release workflow spends MineSkin quota
on it. Also runs on pull requests.

    python tools/validate.py
"""

import re
import struct
import sys
from pathlib import Path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# The name is the lookup key the server uses, so it has to be a legal Java-style
# constant: the plugin resolves skins by exactly this string.
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# 64x64 is the modern layout. 64x32 is the pre-1.8 one - four skins genuinely use
# it (DIANGO, DUKE_HORATIO, SRAM, WEREWOLF) and Minecraft still renders them, so
# rejecting it would fail the seed.
VALID_SIZES = ((64, 64), (64, 32))


def png_size(data):
    if not data.startswith(PNG_MAGIC) or len(data) < 24:
        return None
    return struct.unpack(">II", data[16:24])


def validate(skins_dir):
    errors = []
    paths = sorted(Path(skins_dir).iterdir())

    if not paths:
        return ["skins/ is empty"]

    for path in paths:
        rel = "skins/" + path.name

        if path.is_dir():
            errors.append(rel + ": directories are not allowed under skins/")
            continue
        if path.suffix != ".png":
            errors.append(rel + ": only .png files are allowed (skins need an alpha channel; jpg cannot store one)")
            continue
        if not NAME_RE.match(path.stem):
            errors.append(rel + ": filename must be an UPPER_SNAKE_CASE skin name")
            continue

        data = path.read_bytes()
        size = png_size(data)
        if size is None:
            errors.append(rel + ": not a valid PNG (bad magic bytes or truncated header)")
        elif size not in VALID_SIZES:
            errors.append(rel + ": is " + str(size[0]) + "x" + str(size[1]) + ", expected 64x64 or 64x32")

    return errors


def main():
    root = Path(__file__).resolve().parent.parent
    errors = validate(root / "skins")
    if errors:
        for e in errors:
            print("ERROR " + e, file=sys.stderr)
        print("")
        print(str(len(errors)) + " problem(s) found", file=sys.stderr)
        return 1
    count = len(list((root / "skins").glob("*.png")))
    print("ok - " + str(count) + " skins validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
