"""
Parses the legacy Skins.java enum out of the minescape.me plugin.

Used once, by seed.py, to bootstrap this repository. The enum is deleted from the
plugin afterwards, so this module has no job after the seed - it is kept so the
seed can be re-run and re-verified against the original source.

Mirrors minescape-content/tools/export_enums.py::export_skins, which is the
implementation this was checked against.
"""

import re
from pathlib import Path

# A Java identifier followed by '(' - the start of an enum constant. The lookbehind
# stops us matching the tail of a longer name.
ENTRY_START = re.compile(r"(?<![A-Za-z0-9_$])([A-Z][A-Z0-9_]*)\s*\(")

JAVA_STR = re.compile(r'^"((?:[^"\\]|\\.)*)"$')

SUPER_CALL = re.compile(
    r'super\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*\)', re.S
)

GET_DISPLAY = re.compile(
    r"public\s+String\s+getDisplay\(\)\s*\{.*?return\s+(.*?);", re.S
)


def strip_comments(text):
    """
    Drops // line comments and /* */ blocks.

    This matters more than it looks: five constants (ALRENA, EDMOND, GERALD,
    HADLEY, ALMERA) have commented-out duplicates in Skins.java, and for ALRENA
    and EDMOND the commented copy is the *newer* upload. Leaving them in would
    silently pick the wrong texture for those two.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(l for l in text.split("\n") if not l.strip().startswith("//"))


def _split_top_level(argstr):
    """Splits a Java argument list on commas not inside a string or nested parens."""
    args, buf, depth, in_str, escaped = [], [], 0, False, False
    for ch in argstr:
        if in_str:
            buf.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            buf.append(ch)
        elif ch in "([":
            depth += 1
            buf.append(ch)
        elif ch in ")]":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        args.append("".join(buf).strip())
    return args


def _read_args(text, open_paren):
    """Given the index of '(', returns (argstring, index just past the matching ')')."""
    depth, i, in_str, escaped = 0, open_paren, False, False
    while i < len(text):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1 : i], i + 1
        i += 1
    raise ValueError("unbalanced parentheses in enum body")


def _as_string(arg):
    m = JAVA_STR.match(arg.strip())
    if not m:
        return None
    return m.group(1).encode().decode("unicode_escape")


def subclass_textures(skin_dir):
    """
    Maps subclass simple name -> (texture, signature, display).

    The 27 class-backed constants wrap a file under npc/ or player/ whose
    constructor calls super("texture", "signature"). Ten of the player/ ones also
    override getDisplay() with a custom label.
    """
    out = {}
    for path in sorted(skin_dir.glob("npc/*.java")) + sorted(skin_dir.glob("player/*.java")):
        src = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        m = SUPER_CALL.search(src)
        if not m:
            continue
        display = None
        d = GET_DISPLAY.search(src)
        if d:
            display = _as_string(d.group(1).strip())
        out[path.stem] = (
            m.group(1).encode().decode("unicode_escape"),
            m.group(2).encode().decode("unicode_escape"),
            display,
        )
    return out


def parse(skin_dir):
    """
    Returns an ordered list of (name, texture, signature, display).

    Raises on a duplicate name or an entry it cannot resolve - a silent skip here
    would mean a skin quietly vanishing from the server.
    """
    skin_dir = Path(skin_dir)
    src = strip_comments((skin_dir / "Skins.java").read_text(encoding="utf-8", errors="replace"))

    body = src.split("public enum Skins{", 1)[1]
    # The constant list ends at the lone ';' that closes it.
    body = re.split(r"^\s*;\s*$", body, maxsplit=1, flags=re.M)[0]

    classes = subclass_textures(skin_dir)

    entries, seen, pos = [], set(), 0
    while True:
        m = ENTRY_START.search(body, pos)
        if not m:
            break
        name = m.group(1)
        argstr, pos = _read_args(body, m.end() - 1)
        args = _split_top_level(argstr)

        texture = signature = display = None
        if len(args) >= 2 and _as_string(args[0]) and _as_string(args[1]):
            texture, signature = _as_string(args[0]), _as_string(args[1])
        elif args:
            cm = re.match(r"new\s+(\w+)\s*\(\s*\)", args[0])
            if cm and cm.group(1) in classes:
                texture, signature, display = classes[cm.group(1)]

        if not texture or not signature:
            raise ValueError("Skins." + name + ": could not resolve texture/signature")
        if name in seen:
            raise ValueError("Skins." + name + ": duplicate constant")
        seen.add(name)
        entries.append((name, texture, signature, display))

    return entries
