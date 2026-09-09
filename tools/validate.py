"""
Checks everything under skins/ before the release workflow spends MineSkin quota on it.

Runs on pull requests. With --markdown it also writes a report the workflow posts as a
PR comment, so a contributor sees exactly which files failed and why.

    python tools/validate.py
    python tools/validate.py --markdown report.md
"""

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from regions import REGIONS
from skinfile import NAME_RE, VALID_SIZES, iter_skins

ROOT = Path(__file__).resolve().parent.parent
SKINS = ROOT / "skins"

# Rows in the PR comment before it is truncated - GitHub caps comment length.
MAX_REPORTED = 40


def validate(skins_dir):
    """Returns a list of (relpath, message). An empty list means everything is fine."""
    errors = []
    files = iter_skins(skins_dir)

    if not files:
        return [("skins/", "no skin files found")]

    for f in files:
        if f.region is None:
            errors.append((f.relpath, "sits loose in skins/ - put it in a region folder, e.g. skins/misthalin/"
                                      + f.path.name))
            continue
        if f.region not in REGIONS:
            errors.append((f.relpath, "'" + f.region + "' is not a region folder. Use one of: "
                                      + ", ".join(REGIONS)))
            continue
        if f.depth > 1:
            errors.append((f.relpath, "is nested too deep - skins go directly in skins/<region>/"))
            continue

        if f.path.suffix != ".png":
            errors.append((f.relpath, "only .png is allowed - skins need an alpha channel, which jpg cannot store"))
            continue
        if not NAME_RE.match(f.name):
            errors.append((f.relpath, "'" + f.name + "' must be UPPER_SNAKE_CASE. Name a slim skin "
                                      + "NAME.slim.png, not NAME.SLIM.png"))
            continue

        size = f.size()
        if size is None:
            errors.append((f.relpath, "is not a valid PNG (bad magic bytes or truncated header)"))
        elif size not in VALID_SIZES:
            errors.append((f.relpath, "is " + str(size[0]) + "x" + str(size[1]) + ", expected 64x64 or 64x32"))

    # The server resolves a skin by name with no idea which folder it came from, so two
    # files sharing a name would silently shadow each other in the manifest.
    by_name = collections.defaultdict(list)
    for f in files:
        if f.region in REGIONS and f.path.suffix == ".png":
            by_name[f.name].append(f)
    for name, dupes in sorted(by_name.items()):
        if len(dupes) > 1:
            where = ", ".join(d.relpath for d in dupes)
            for d in dupes:
                errors.append((d.relpath, "duplicate skin name '" + name + "' - also defined by " + where
                                          + ". Names must be unique across every region folder."))

    return errors


def markdown_report(errors, total):
    if not errors:
        return ("### Skin validation passed\n\n" + str(total) + " skins checked.\n")

    by_file = collections.OrderedDict()
    for relpath, message in errors:
        by_file.setdefault(relpath, []).append(message)

    lines = ["### Skin validation failed",
             "",
             str(len(by_file)) + " file(s) need fixing before this can merge.",
             "",
             "| File | Problem |",
             "| --- | --- |"]

    # A comment has a hard size limit on GitHub, and a wholesale mistake can fail every
    # file at once. Show enough to act on and say how many more there are.
    shown = 0
    for relpath, messages in by_file.items():
        if shown >= MAX_REPORTED:
            break
        for message in messages:
            lines.append("| `" + relpath + "` | " + message.replace("|", "\\|") + " |")
        shown += 1
    if len(by_file) > shown:
        lines += ["", "...and " + str(len(by_file) - shown) + " more file(s) with the same kinds of problem. "
                      + "Run `python tools/validate.py` locally to see all of them."]

    lines += ["",
              "<details><summary>Naming rules</summary>",
              "",
              "- One PNG per skin at `skins/<region>/<NAME>.png`",
              "- `<NAME>` is `UPPER_SNAKE_CASE` and must be unique across **all** region folders",
              "- End the file `.slim.png` for an Alex-model skin - the `.slim` is stripped from the name",
              "- 64x64 (or legacy 64x32), PNG only",
              "- Regions: " + ", ".join("`" + r + "`" for r in REGIONS),
              "</details>",
              ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", type=Path, help="write a PR-comment report to this path")
    args = ap.parse_args()

    errors = validate(SKINS)
    total = sum(1 for f in iter_skins(SKINS) if f.path.suffix == ".png")

    if args.markdown:
        args.markdown.write_text(markdown_report(errors, total), encoding="utf-8")

    if errors:
        for relpath, message in errors:
            print("ERROR " + relpath + ": " + message, file=sys.stderr)
        print("", file=sys.stderr)
        print(str(len(errors)) + " problem(s) found", file=sys.stderr)
        return 1

    print("ok - " + str(total) + " skins validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
