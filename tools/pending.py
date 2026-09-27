"""
Textures Mojang has already signed, folded into the manifest on merge without an upload.

A contributor who put their skins on a Minecraft account already holds, for each one, the
signed texture property Mojang issued. Re-uploading those spends MineSkin quota to get
back a texture no better than the one they already have - and for a batch of several
hundred it stretches a merge across hours of quota windows.

A JSON file under pending/ carries those texture/signature pairs. On merge the release run
copies them straight into the manifest and uploads nothing. The file is additive and never
has to be cleaned up: an entry is only consulted for a skin whose image actually changed,
so once it has been folded in it stops matching anything.

None of it is taken on the contributor's word. Before an entry can reach the manifest it is
checked against Mojang itself:

  1. the signature verifies against Mojang's published profile-property public keys, so the
     texture was signed by Mojang rather than assembled by hand,
  2. the signed payload points at textures.minecraft.net, and its model (Steve/Alex) matches
     the .slim marker on the filename, and
  3. the image Mojang serves is, pixel for pixel, the PNG in this repository - so an entry
     cannot point a skin name at some other texture.

    python tools/pending.py --add BANDIT --profile SomeAccountName   # build an entry
    python tools/pending.py --check                                  # verify them all
"""

import argparse
import base64
import io
import json
import sys
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from skinfile import NAME_RE, iter_skins

ROOT = Path(__file__).resolve().parent.parent
SKINS = ROOT / "skins"
PENDING = ROOT / "pending"

# Where Mojang publishes the keys it signs profile properties with. Fetching them beats
# pinning a copy here: a key rotation would silently invalidate a pinned one, and these
# come from Mojang over HTTPS anyway, which is the whole point of the check.
PUBLIC_KEYS_URL = "https://api.minecraftservices.com/publickeys"
PROFILE_URL = "https://sessionserver.mojang.com/session/minecraft/profile/"
UUID_URL = "https://api.mojang.com/users/profiles/minecraft/"
TEXTURE_HOST = "textures.minecraft.net"

USER_AGENT = "MineScapeSkinPending/1.0 (+https://github.com/AshleyThew/minescape-skins)"
TIMEOUT = 30

# Rows in the PR comment before it is truncated - GitHub caps comment length.
MAX_REPORTED = 40


class PendingError(Exception):
    """Something the caller did wrong, phrased for them rather than as a stack trace."""


def session():
    """
    One connection, reused, that retries a dropped request.

    A large contribution checks several hundred textures in a row, and over that many
    requests Mojang's CDN will occasionally close a connection or answer 503. Without a
    retry a single blip rejects an entry that is perfectly good - red pull request, and an
    upload at merge time that was never needed.
    """
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    retry = Retry(total=4, connect=4, read=4, backoff_factor=0.5,
                  status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


# --------------------------------------------------------------------- reading pending/

def load(pending_dir=PENDING):
    """
    Returns (entries, errors).

    `entries` maps skin name -> {"texture", "signature", "source"}. `errors` is the same
    (source, message) shape validate.py produces, so both reports read alike.
    """
    entries = {}
    errors = []
    pending_dir = Path(pending_dir)
    if not pending_dir.exists():
        return entries, errors

    for path in sorted(pending_dir.rglob("*.json")):
        relpath = path.relative_to(ROOT).as_posix()
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            errors.append((relpath, "is not valid JSON: " + str(e)))
            continue

        skins = doc.get("skins", doc) if isinstance(doc, dict) else None
        if not isinstance(skins, dict):
            errors.append((relpath, 'must be an object of skin name -> {"texture", "signature"}, '
                                    'optionally wrapped in a "skins" key'))
            continue

        for name, value in skins.items():
            if not isinstance(value, dict):
                errors.append((relpath, "'" + str(name) + "' must be an object with a texture and a signature"))
                continue
            if not NAME_RE.match(str(name)):
                errors.append((relpath, "'" + str(name) + "' is not a valid skin name (UPPER_SNAKE_CASE)"))
                continue
            texture, signature = value.get("texture"), value.get("signature")
            if not texture or not signature:
                errors.append((relpath, "'" + name + "' needs both a texture and a signature"))
                continue
            if name in entries and entries[name]["texture"] != texture:
                errors.append((relpath, "'" + name + "' is also defined in " + entries[name]["source"]
                                        + " with a different texture - keep one"))
                continue
            entries[name] = {"texture": texture, "signature": signature, "source": relpath}

    return entries, errors


# ------------------------------------------------------------------------ Mojang checks

def public_keys(http):
    """Mojang's current profile-property signing keys."""
    try:
        r = http.get(PUBLIC_KEYS_URL, timeout=TIMEOUT)
        r.raise_for_status()
        published = r.json().get("profilePropertyKeys") or []
    except Exception as e:
        raise PendingError("could not read Mojang's public keys from " + PUBLIC_KEYS_URL + ": " + str(e))

    keys = []
    for item in published:
        try:
            keys.append(serialization.load_der_public_key(base64.b64decode(item["publicKey"])))
        except Exception:
            continue
    if not keys:
        raise PendingError("Mojang published no usable profile-property keys")
    return keys


def signature_is_mojangs(texture, signature, keys):
    """Mojang signs the base64 texture value itself: SHA1withRSA, PKCS#1 v1.5."""
    try:
        raw = base64.b64decode(signature, validate=True)
    except Exception:
        return False
    message = texture.encode("ascii", "ignore")
    for key in keys:
        try:
            key.verify(raw, message, padding.PKCS1v15(), hashes.SHA1())
            return True
        except InvalidSignature:
            continue
        except Exception:
            continue
    return False


def texture_payload(texture):
    """The JSON Mojang signed, or None when this is not a texture property at all."""
    try:
        return json.loads(base64.b64decode(texture))
    except Exception:
        return None


def skin_texture(payload):
    """(url, model) out of a signed payload. `model` is 'slim' (Alex) or 'classic' (Steve)."""
    skin = ((payload or {}).get("textures") or {}).get("SKIN") or {}
    url = skin.get("url")
    if not isinstance(url, str):
        return None, None
    model = (skin.get("metadata") or {}).get("model") or "classic"
    return url.replace("http://", "https://", 1), model


def _pixels(data):
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        return image.convert("RGBA")
    except Exception:
        return None


def images_match(remote, local):
    """
    True when Mojang is serving this exact skin.

    Byte equality is the common case but is not guaranteed - Mojang re-encodes the PNG it
    stores, so the same picture comes back with different chunks. Compare what the game
    would actually render instead, and treat a fully transparent pixel as equal whatever
    colour is hiding under its zero alpha, which re-encoding is free to drop.
    """
    if remote == local:
        return True
    a, b = _pixels(remote), _pixels(local)
    if a is None or b is None or a.size != b.size:
        return False
    ap, bp = a.tobytes(), b.tobytes()
    if ap == bp:
        return True
    for i in range(0, len(ap), 4):
        if ap[i + 3] == 0 and bp[i + 3] == 0:
            continue
        if ap[i:i + 4] != bp[i:i + 4]:
            return False
    return True


def verify(entries, files, http=None, keys=None, cache=None):
    """
    Checks every pending entry against Mojang.

    Returns (accepted, errors). `accepted` maps skin name -> a manifest entry ready to drop
    in; `errors` is (source file, message) for everything rejected.
    """
    accepted = {}
    errors = []
    if not entries:
        return accepted, errors

    http = http or session()
    keys = keys or public_keys(http)
    cache = {} if cache is None else cache

    for name in sorted(entries):
        entry = entries[name]
        source = entry["source"]

        skin = files.get(name)
        if skin is None:
            errors.append((source, "'" + name + "' has no PNG under skins/ - add the image, or drop the entry"))
            continue

        payload = texture_payload(entry["texture"])
        url, model = skin_texture(payload)
        if url is None:
            errors.append((source, "'" + name + "' is not a Mojang texture property - it does not decode "
                                   "to JSON with textures.SKIN.url"))
            continue
        if not url.startswith("https://" + TEXTURE_HOST + "/"):
            errors.append((source, "'" + name + "' points at " + url.split("/texture/")[0]
                                   + ", not " + TEXTURE_HOST))
            continue

        if not signature_is_mojangs(entry["texture"], entry["signature"], keys):
            errors.append((source, "'" + name + "' signature does not verify against Mojang's public keys - "
                                   "texture and signature have to be the pair Mojang issued, copied verbatim"))
            continue

        wanted = "slim" if skin.slim else "classic"
        if model != wanted:
            errors.append((source, "'" + name + "' is a " + model + " texture but " + skin.relpath
                                   + " asks for " + wanted + " - rename the file, or sign the other model"))
            continue

        if url not in cache:
            try:
                r = http.get(url, timeout=TIMEOUT)
                r.raise_for_status()
                cache[url] = r.content
            except Exception as e:
                errors.append((source, "'" + name + "' texture could not be downloaded from Mojang: " + str(e)))
                continue
        if not images_match(cache[url], skin.read()):
            errors.append((source, "'" + name + "' is not the image Mojang serves for that texture - "
                                   "re-sign it from the PNG in this pull request"))
            continue

        accepted[name] = {
            "texture": entry["texture"],
            "signature": entry["signature"],
            "texture_url": url,
            "source": source,
        }

    return accepted, errors


# --------------------------------------------------------------------- building entries

def resolve_profile(profile, http=None):
    """(texture, signature) for the skin a Minecraft account is wearing right now."""
    http = http or session()
    uuid = profile.replace("-", "")
    if len(uuid) != 32:
        r = http.get(UUID_URL + profile, timeout=TIMEOUT)
        if r.status_code == 404 or not r.content:
            raise PendingError("no Minecraft account called '" + profile + "'")
        r.raise_for_status()
        uuid = r.json()["id"]

    r = http.get(PROFILE_URL + uuid + "?unsigned=false", timeout=TIMEOUT)
    if r.status_code == 429:
        raise PendingError("Mojang is rate limiting profile lookups - wait a minute and try again")
    r.raise_for_status()
    for prop in r.json().get("properties", []):
        if prop.get("name") == "textures" and prop.get("signature"):
            return prop["value"], prop["signature"]
    raise PendingError("Mojang returned no signed texture for " + profile
                       + " - the account has no skin set")


def add(path, name, texture, signature):
    """Writes one entry into a pending file, keeping whatever is already there."""
    doc = {"skins": {}}
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        doc = loaded if isinstance(loaded, dict) and "skins" in loaded else {"skins": loaded}
    doc["skins"][name] = {"texture": texture, "signature": signature}
    doc["skins"] = dict(sorted(doc["skins"].items()))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- reporting

def markdown_report(accepted, errors, total):
    """A section for the PR comment. Empty when the PR has no pending textures at all."""
    if not total and not errors:
        return ""

    if not errors:
        return "\n".join(["### Pending textures verified",
                          "",
                          str(len(accepted)) + " pre-signed texture(s) checked out against Mojang and go "
                          "straight into the manifest. Merging will not upload them.",
                          ""])

    lines = ["### Pending textures rejected",
             "",
             str(len(errors)) + " pending entry(s) did not check out against Mojang"
             + (", " + str(len(accepted)) + " did" if accepted else "") + ".",
             "",
             "| Source | Problem |",
             "| --- | --- |"]
    for source, message in errors[:MAX_REPORTED]:
        lines.append("| `" + source + "` | " + message.replace("|", "\\|") + " |")
    if len(errors) > MAX_REPORTED:
        lines += ["", "...and " + str(len(errors) - MAX_REPORTED) + " more."]
    lines += ["",
              "<details><summary>What is checked</summary>",
              "",
              "- the signature verifies against Mojang's published profile-property keys",
              "- the signed payload points at `textures.minecraft.net`",
              "- the model (Steve/Alex) matches the `.slim` marker on the filename",
              "- Mojang serves exactly the PNG in this pull request for that texture",
              "",
              "Build an entry with `python tools/pending.py --add NAME --profile <account>`.",
              "</details>",
              ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Verify or build pending/ texture entries.")
    ap.add_argument("--check", action="store_true", help="verify every pending entry against Mojang")
    ap.add_argument("--markdown", type=Path, help="write a PR-comment report to this path")
    ap.add_argument("--add", metavar="NAME", help="add or replace one entry")
    ap.add_argument("--profile", help="--add from the skin this Minecraft account is wearing")
    ap.add_argument("--texture", help="--add from a texture property value you already hold")
    ap.add_argument("--signature", help="the signature for --texture")
    ap.add_argument("--file", type=Path, default=PENDING / "skins.json",
                    help="pending file to write to (default pending/skins.json)")
    args = ap.parse_args()

    if args.add:
        try:
            if not NAME_RE.match(args.add):
                raise PendingError("'" + args.add + "' is not a valid skin name (UPPER_SNAKE_CASE)")
            if args.profile:
                texture, signature = resolve_profile(args.profile)
            elif args.texture and args.signature:
                texture, signature = args.texture, args.signature
            else:
                raise PendingError("--add needs either --profile, or both --texture and --signature")
            add(args.file, args.add, texture, signature)
        except PendingError as e:
            print("ERROR " + str(e), file=sys.stderr)
            return 1
        print("wrote " + args.add + " to " + str(args.file))
        if not args.check:
            return 0

    accepted = {}
    entries, errors = load()
    if entries:
        files = {f.name: f for f in iter_skins(SKINS) if f.path.suffix == ".png"}
        try:
            accepted, verify_errors = verify(entries, files)
            errors += verify_errors
        except PendingError as e:
            # Mojang itself being unreachable is reported like any other rejection, so the
            # pull request says why rather than going red with an empty comment.
            errors.append(("pending/", str(e)))

    if args.markdown:
        args.markdown.write_text(markdown_report(accepted, errors, len(entries)), encoding="utf-8")

    if not entries and not errors:
        print("no pending textures")
        return 0

    for name in sorted(accepted):
        print("ok    " + name + "  (" + accepted[name]["source"] + ")")
    for source, message in errors:
        print("ERROR " + source + ": " + message, file=sys.stderr)

    print("")
    print(str(len(accepted)) + " verified against Mojang, " + str(len(errors)) + " rejected")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
