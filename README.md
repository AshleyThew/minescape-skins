# minescape-skins

Source images for every NPC and player skin on [MineScape](https://minescape.me), and the pipeline that turns them into something the server can load at runtime.

Each skin is one PNG under [`skins/`](skins), named after the key the server looks it up by. Open a pull request and CI uploads the changed images to [MineSkin](https://mineskin.org) and updates `manifest.json` on your branch; merging publishes that manifest as a GitHub release. The server plugin pulls the release on startup, verifies its SHA-256, and swaps the skins in — no plugin rebuild, no redeploy.

## Adding or changing a skin

`main` takes pull requests only, so every change goes through one.

1. Branch, and drop a **64×64 PNG** into `skins/`, named in `UPPER_SNAKE_CASE` — the filename *is* the name the server and the dialogue editor use (`skins/MAGE_OF_ZAMORAK.png` → `MAGE_OF_ZAMORAK`).
2. Open a PR. CI validates the image, uploads the changed ones to MineSkin, and **commits the updated `manifest.json` onto your PR branch** — so the texture and signature the server will use are visible in the diff before anything ships.
3. Merge. CI publishes the manifest as a release; it uploads nothing, because the PR already did.
4. The change reaches every region on the next server start, or immediately with `/skins pull`.

A PR cannot merge while `manifest.json` disagrees with the images beside it, and `main` refuses to publish a manifest that does not describe them.

To replace an existing skin, overwrite its PNG — keep the filename and the server keeps the reference.

### Why PNG and not JPG

Minecraft skins need an alpha channel for the hat and jacket overlay layers, and JPEG is lossy, so it shifts the exact pixel colours the model relies on. A JPEG skin renders with opaque black boxes over the overlays. `tools/validate.py` rejects anything that is not a PNG.

Both 64×64 and the pre-1.8 64×32 layout are accepted — four skins (`DIANGO`, `DUKE_HORATIO`, `SRAM`, `WEREWOLF`) are genuinely 64×32. New skins should be 64×64.

## `manifest.json`

Generated, committed, and published as a release asset.

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
      "display":      "The Noob"
    }
  }
}
```

`texture` and `signature` are the Mojang texture property and its signature — what the server puts on a `GameProfile`. `display` is an optional label; without it the server derives one from the name.

`image_sha256` is the digest of the PNG in this repo, and it is what makes incremental uploads work: CI re-uploads a skin only when its image digest changes. **Unchanged entries are copied through byte-for-byte, so working signatures are never regenerated.**

## Tools

| | |
|---|---|
| `tools/validate.py` | Filename, PNG format and dimension checks. Runs on PRs and before any upload. |
| `tools/build_manifest.py --check` | Reports which skins would be uploaded. Uploads nothing, needs no API key. |
| `tools/build_manifest.py --verify` | Same, but exits non-zero if the manifest and the images disagree. Gates PRs and releases. |
| `tools/build_manifest.py --upload` | Uploads changed skins and rewrites the manifest. Used by CI. |
| `tools/upload.py` | MineSkin v2 client. |
| `tools/seed.py` | One-time bootstrap from the old `Skins.java` enum. Kept so the seed stays reproducible. |
| `tools/skins_source.py` | Parser for that enum. |

`build_manifest.py` refuses to upload more than 50 skins in one run; pass `--force-all` if a bulk re-upload really is intended.

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
