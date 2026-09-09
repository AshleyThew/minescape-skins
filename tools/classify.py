"""
Sorts skins into region folders.

Sources, in priority order:

0. Player skins (the starting bodies and holiday costumes) are always `multi`.
1. A skintrait in the MineScape dialogue tree, which is filed by city. The strongest
   signal - it says where *this server* actually uses the skin, not where the wiki says
   the NPC stands. Cities in two different regions mean `multi`.
2. tools/region_overrides.json saying `multi`. A generic NPC type (archer, soldier,
   tanner) has dialogue in one town but exists everywhere, so "appears all over" beats
   the single filename match below.
3. A dialogue file *named* after the skin (draynor/joe.json for JOE). Weaker than a
   skintrait, but it places 37 skins nothing else reaches, and where it contradicts the
   wiki it is still this server's own answer.
4. tools/region_overrides.json, researched from the OSRS Wiki and committed so the
   classification is reviewable and correctable.

Anything no source places goes to `other` rather than being guessed at.

    python tools/classify.py --dialogue ../MineScape/dialogue/regions          # dry run
    python tools/classify.py --dialogue ../MineScape/dialogue/regions --apply
"""

import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from regions import CITY_TO_REGION, MULTI, OTHER, PLAYER_SKINS, REGIONS
from skinfile import iter_skins

ROOT = Path(__file__).resolve().parent.parent
SKINS = ROOT / "skins"
OVERRIDES = Path(__file__).parent / "region_overrides.json"

SKIN_REF = re.compile(r'"skin"\s*:\s*"([A-Z][A-Z0-9_]*)"')


def regions_from_dialogue(dialogue_root):
    """
    Two views of the dialogue tree, both keyed by skin name:

    `refs`  - a dialogue file in that city sets this skin on an NPC. Direct evidence.
    `files` - a dialogue file in that city is *named* after the skin (draynor/joe.json
              for JOE). Weaker, but it places 41 skins no skintrait references.
    """
    dialogue_root = Path(dialogue_root)
    if not dialogue_root.exists():
        sys.exit("dialogue folder not found: " + str(dialogue_root))

    base = len(dialogue_root.parts)
    refs = collections.defaultdict(set)
    files = collections.defaultdict(set)
    unknown_cities = set()

    for path in dialogue_root.rglob("*.json"):
        parts = path.parts
        if len(parts) <= base:
            continue
        city = parts[base]
        region = CITY_TO_REGION.get(city)
        if region is None:
            unknown_cities.add(city)
            continue
        for name in set(SKIN_REF.findall(path.read_text(encoding="utf-8", errors="replace"))):
            refs[name].add(region)
        files[path.stem.upper()].add(region)

    return refs, files, unknown_cities


def load_overrides():
    if not OVERRIDES.exists():
        return {}
    raw = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    out = {}
    for name, value in raw.items():
        region = value["region"] if isinstance(value, dict) else value
        if region not in REGIONS:
            sys.exit("region_overrides.json: '" + region + "' for " + name + " is not a region folder")
        out[name] = region
    return out


def target_region(name, refs, files, overrides):
    # Wearable by any player anywhere, so never a region.
    if name in PLAYER_SKINS:
        return MULTI, "player skin"

    hits = refs.get(name)
    if hits:
        # A city folder literally named "multi" already means "used all over".
        if MULTI in hits:
            return MULTI, "skintrait"
        if len(hits) > 1:
            return MULTI, "skintrait (" + str(len(hits)) + " regions)"
        return next(iter(hits)), "skintrait"

    # A generic NPC type - archer, soldier, tanner, bartender - has dialogue in one town
    # but exists in many. Research saying "this appears all over" beats a single filename.
    if overrides.get(name) == MULTI:
        return MULTI, "wiki (generic)"

    hits = files.get(name)
    if hits:
        if MULTI in hits:
            return MULTI, "dialogue file"
        if len(hits) > 1:
            return MULTI, "dialogue file (" + str(len(hits)) + " regions)"
        return next(iter(hits)), "dialogue file"

    if name in overrides:
        return overrides[name], "wiki"
    return OTHER, "unplaced"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dialogue", required=True, help="path to MineScape/dialogue/regions")
    ap.add_argument("--apply", action="store_true", help="actually move the files")
    args = ap.parse_args()

    refs, files_by_name, unknown_cities = regions_from_dialogue(args.dialogue)
    overrides = load_overrides()

    if unknown_cities:
        print("dialogue folders with no region mapping (add them to tools/regions.py):")
        for city in sorted(unknown_cities):
            print("  " + city)
        print("")

    files = [f for f in iter_skins(SKINS) if f.path.suffix == ".png"]
    moves, tally, sources = [], collections.Counter(), collections.Counter()

    for f in sorted(files, key=lambda x: x.name):
        region, source = target_region(f.name, refs, files_by_name, overrides)
        tally[region] += 1
        sources[source] += 1
        destination = SKINS / region / f.path.name
        if f.path.resolve() != destination.resolve():
            moves.append((f, destination))

    print("region tally:")
    for region in REGIONS:
        if tally[region]:
            print("  %-20s %3d" % (region, tally[region]))
    print("")
    print("classified by: " + ", ".join(k + "=" + str(v) for k, v in sources.most_common()))
    print(str(len(moves)) + " file(s) to move")

    if not args.apply:
        for f, destination in moves[:15]:
            print("  " + f.relpath + "  ->  " + destination.relative_to(SKINS).as_posix())
        if len(moves) > 15:
            print("  ... and " + str(len(moves) - 15) + " more")
        print("")
        print("dry run - pass --apply to move them")
        return 0

    for f, destination in moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # git mv keeps the rename visible in history rather than showing a delete plus an add.
        result = subprocess.run(["git", "mv", str(f.path), str(destination)], cwd=str(ROOT),
                                capture_output=True, text=True)
        if result.returncode != 0:
            f.path.rename(destination)

    # Leave no empty region folders behind from a previous layout.
    for folder in sorted(SKINS.rglob("*"), reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()

    print("moved " + str(len(moves)) + " file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
