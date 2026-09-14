# `pending/`

Textures Mojang has **already signed**, so merging does not re-upload them.

Normally merging a skin sends its PNG to MineSkin, which hands it to Mojang and gets a
signed texture back. If you already put the skin on a Minecraft account, Mojang signed it
the moment you did — that texture is just as good, costs no MineSkin quota, and is the
exact one you were looking at in game. Drop it in a JSON file here and the release run
copies it into the manifest instead of uploading anything.

## Building an entry

Wear the skin on a Minecraft account, then:

```bash
python tools/pending.py --add BANDIT --profile YourAccountName
```

That reads the signed texture straight from Mojang's session server and writes it to
`pending/skins.json`. Repeat per skin. If you already hold the pair, pass it directly:

```bash
python tools/pending.py --add BANDIT --texture "ewogICJ0aW1..." --signature "MHYJfOG..."
```

Check the whole folder before pushing:

```bash
python tools/pending.py --check
```

## Format

Any `.json` file in this folder, so a big contribution can be split into several:

```json
{
  "skins": {
    "BANDIT": {
      "texture": "ewogICJ0aW1lc3RhbXAiIDog…",
      "signature": "MHYJfOGuGNCRM0sx+5m2m1i0WiB9…"
    }
  }
}
```

`texture` is the base64 texture property value and `signature` is Mojang's signature over
it, both copied verbatim — they are a pair and neither works without the other.

## What is checked

Every entry is verified against Mojang on the pull request, and again on merge before it
can reach the manifest:

- the signature verifies against Mojang's [published profile-property public keys](https://api.minecraftservices.com/publickeys), so the texture was signed by Mojang and not written by hand
- the signed payload points at `textures.minecraft.net`
- the model matches the file: a `.slim.png` needs an Alex texture, a plain `.png` a Steve one
- the image Mojang serves for that texture is, pixel for pixel, the PNG in this repository

An entry that fails is not fatal — that skin is uploaded to MineSkin the normal way — but
CI says so on the pull request, because it usually means the texture and the image have
drifted apart.

## Cleaning up

Nothing to clean up. An entry is only consulted for a skin whose image changed, so once it
has been folded into the manifest it stops matching and sits here as a record of where that
texture came from.
