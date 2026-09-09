# minescape-skins

Source images for every NPC and player skin on [MineScape](https://minescape.me), and the pipeline that turns them into something the server can load at runtime.

Each skin is one PNG under [`skins/`](skins), filed by OSRS region and named after the key the server looks it up by. A pull request is only checked; **merging** is what uploads the changed images to [MineSkin](https://mineskin.org) and publishes a new manifest as a GitHub release. The server plugin pulls that release on startup, verifies its SHA-256, and swaps the skins in — no plugin rebuild, no redeploy.

## Adding or changing a skin

`main` takes pull requests only, so every change goes through one.

1. Branch, and drop a **64×64 PNG** into the region folder the NPC belongs to, named in `UPPER_SNAKE_CASE` — the filename *is* the name the server and the dialogue editor use (`skins/kandarin/MAGE_OF_ZAMORAK.png` → `MAGE_OF_ZAMORAK`).
2. Open a PR. CI validates names, regions, duplicates and image format, and comments on anything wrong. **Nothing is uploaded** — a PR you revise ten times, or close unmerged, costs no MineSkin quota. It also prints what merging *would* upload.
3. Merge. CI uploads the changed images, rebuilds the manifest and publishes it as a release.
4. The change reaches every region on the next server start, or immediately with `/skins pull`.

To replace an existing skin, overwrite its PNG — keep the filename and the server keeps the reference. Moving a skin to a different region folder is free: it renames nothing and costs no upload.

## Region folders

Folders are OSRS world regions, not cities:

`asgarnia` · `feldip_hills` · `fremennik_province` · `great_kourend` · `kandarin` · `karamja` · `kebos_lowlands` · `kharidian_desert` · `misthalin` · `morytania` · `tirannwn` · `troll_country` · `varlamore` · `wilderness`

plus two that are not places:

- **`multi`** — used across more than one region: generic NPCs (guards, bartenders, `MAN`, `WOMAN`), the default player skins, monsters that spawn all over.
- **`other`** — Tutorial Island, Zanaris, the Abyss, instanced and minigame-only areas, and anything that could not be placed confidently.

**The folder is organisation only.** The server resolves a skin by name and never sees the region, which is why **a name must be unique across every folder** — two files called `BOB.png` in different regions is an error, and CI fails the PR and comments which files clashed.

Skins were placed by [`tools/classify.py`](tools/classify.py): first from the MineScape dialogue tree, which is filed by city and says where this server actually uses each skin, and otherwise from [`tools/region_overrides.json`](tools/region_overrides.json), researched from the OSRS Wiki. Correct a placement by moving the file (and the override entry, if it has one).

## Slim (Alex) skins

End the filename `.slim.png` for a 3px-arm Alex model instead of Steve:

```
skins/misthalin/BOB.slim.png   ->  skin name BOB, Alex model
skins/misthalin/BOB.png        ->  skin name BOB, Steve model
```

The `.slim` is a marker, not part of the name — so those two are a **duplicate name clash**, not two different skins.

The model is baked into the signed texture Mojang returns, so switching a skin between Steve and Alex re-uploads it even when the image bytes are identical.

### Why PNG and not JPG

Minecraft skins need an alpha channel for the hat and jacket overlay layers, and JPEG is lossy, so it shifts the exact pixel colours the model relies on. A JPEG skin renders with opaque black boxes over the overlays. `tools/validate.py` rejects anything that is not a PNG.

Both 64×64 and the pre-1.8 64×32 layout are accepted — four skins (`DIANGO`, `DUKE_HORATIO`, `SRAM`, `WEREWOLF`) are genuinely 64×32. New skins should be 64×64.

## `manifest.json`

**Not stored in git.** `main` takes pull requests only, and a personal repository cannot grant GitHub Actions a bypass to commit there, so the published release *is* the store: each run reads the previous release's `manifest.json` as its baseline and publishes a new one. That is also what lets an unchanged skin keep its original texture and signature forever.

```json
{
  "version": 1,
  "generated": "2026-09-09T04:12:33Z",
  "commit": "…",
  "count": 499,
  "skins": {
    "ADAM": {
      "texture":      "ewogICJ0aW1lc3RhbXAi…",
      "signature":    "gGlNQhdpzoXm3Iyt…",
      "image_sha256": "…",
      "texture_url":  "https://textures.minecraft.net/texture/…",
      "region":       "misthalin",
      "slim":         true,
      "display":      "The Noob"
    }
  }
}
```

`texture` and `signature` are the Mojang texture property and its signature — what the server puts on a `GameProfile`. `display` is an optional label; without it the server derives one from the name. `region` and `slim` mirror the file's folder and its `.slim.png` suffix, and are re-derived on every run, so moving or renaming a file updates the manifest without costing an upload. `slim` is omitted for Steve-model skins.

`image_sha256` is the digest of the PNG in this repo, and it is what makes incremental uploads work: CI re-uploads a skin only when its image digest changes. **Unchanged entries are copied through byte-for-byte, so working signatures are never regenerated.**

## Tools

| | |
|---|---|
| `tools/validate.py` | Filename, PNG format and dimension checks. Runs on PRs and before any upload. |
| `tools/build_manifest.py --check` | Reports which skins would be uploaded. Uploads nothing, needs no API key. |
| `tools/build_manifest.py --verify` | Same, but exits non-zero if the published manifest and the images disagree. |
| `tools/build_manifest.py --upload` | Uploads changed skins and writes a new manifest. Used by CI after a merge. |

All three take `--baseline <previous manifest>`; fetch one with `gh release download --pattern manifest.json`.
| `tools/upload.py` | MineSkin v2 client. |
| `tools/classify.py` | Sorts skins into region folders from the dialogue tree plus the wiki overrides. |
| `tools/regions.py` | The region list, and the city-to-region map used for classification. |
| `tools/skinfile.py` | Resolves a path to its skin name, region and model variant. |
| `tools/seed.py` | One-time bootstrap from the old `Skins.java` enum. Kept so the seed stays reproducible. |
| `tools/skins_source.py` | Parser for that enum. |

`build_manifest.py` refuses to **replace** more than 50 existing skins in one run, since each replacement discards a texture and signature that were working; pass `--force-all` if that really is intended. Adding new skins is not capped.

## How the server consumes this

```
https://github.com/AshleyThew/minescape-skins/releases/latest/download/manifest.json
https://github.com/AshleyThew/minescape-skins/releases/latest/download/manifest.json.sha256
```

The plugin fetches the digest first, skips the download when it already has that version, and refuses any manifest whose bytes do not hash to the published digest. It also refuses one that is suspiciously small, so a truncated download can never replace a good skin set. A copy ships inside the plugin jar as an offline fallback.

The digest is served from the same release as the file, so it proves **integrity** — that what arrived is what was published — not authenticity.

## Setup

CI needs one repository secret:

- `MINESKIN_API_KEY` — a [MineSkin](https://mineskin.org) API key.

## History

These 499 skins were previously a 541 KB Java enum inside the server plugin, with the base64 texture blobs pasted in by hand and no source images kept anywhere. The seed recovered every PNG from Mojang's texture CDN and carried the existing texture/signature pairs across unchanged, so nothing was regenerated in the move.
