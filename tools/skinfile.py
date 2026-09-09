"""
Where a skin file lives and what it is called.

Layout is `skins/<region>/<NAME>.png`. The region folder is organisation only - the
server looks a skin up by NAME alone, so a name has to be unique across every region.

A file ending `.slim.png` is an Alex-model skin (3px arms) rather than Steve. The
`.slim` is a marker, not part of the name: `skins/misthalin/BOB.slim.png` is still `BOB`.
"""

import re
import struct
from pathlib import Path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
SLIM_SUFFIX = ".slim.png"
PLAIN_SUFFIX = ".png"

# The lookup key the server and the dialogue editor use.
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# 64x64 is the modern layout. 64x32 is pre-1.8 - four seeded skins genuinely use it, and
# Minecraft still renders them, so rejecting it would fail the existing set.
VALID_SIZES = ((64, 64), (64, 32))


class SkinFile:
    """One PNG under skins/, with its name, region and model variant resolved."""

    def __init__(self, path, root):
        self.path = Path(path)
        self.root = Path(root)
        rel = self.path.relative_to(self.root)
        self.relpath = rel.as_posix()
        # The immediate folder under skins/. None when the file sits loose at the top.
        self.region = rel.parts[0] if len(rel.parts) > 1 else None
        self.depth = len(rel.parts) - 1

        filename = self.path.name
        self.slim = filename.endswith(SLIM_SUFFIX)
        if self.slim:
            self.name = filename[: -len(SLIM_SUFFIX)]
        elif filename.endswith(PLAIN_SUFFIX):
            self.name = filename[: -len(PLAIN_SUFFIX)]
        else:
            self.name = filename

    @property
    def variant(self):
        """What MineSkin calls the model: 'slim' is Alex, 'classic' is Steve."""
        return "slim" if self.slim else "classic"

    def read(self):
        return self.path.read_bytes()

    def size(self):
        """(width, height) from the IHDR chunk, or None if this is not a PNG."""
        data = self.path.read_bytes()
        if not data.startswith(PNG_MAGIC) or len(data) < 24:
            return None
        return struct.unpack(">II", data[16:24])

    def __repr__(self):
        return "SkinFile(" + self.relpath + " -> " + self.name + ")"


def iter_skins(root):
    """Every file under skins/, at any depth, sorted by path. Includes non-PNGs so the validator can complain about them."""
    root = Path(root)
    if not root.exists():
        return []
    return [SkinFile(p, root) for p in sorted(root.rglob("*")) if p.is_file()]
