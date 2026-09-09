"""
MineSkin v2 client.

Ported from MineScape/skins/upload_skins.py, which had the v2 queue contract
right; the changes here are the API key name, retry-on-429, and returning the
result instead of appending Java source to a text file.
"""

import os
import time

import requests

BASE_URL = "https://api.mineskin.org/v2"
USER_AGENT = "MineScapeSkinUploader/2.0 (+https://github.com/AshleyThew/minescape-skins)"

# MineSkin asks for ~1s between status polls and the original script left 3s
# between skins. Keep both - the queue is shared and a 429 costs more than a wait.
POLL_INTERVAL = 1
POLL_ATTEMPTS = 60
BETWEEN_SKINS = 3


class UploadError(Exception):
    pass


def api_key():
    key = os.getenv("MINESKIN_API_KEY") or os.getenv("API_KEY")
    if not key:
        raise UploadError("MINESKIN_API_KEY is not set")
    return key


def _headers(key):
    return {
        "User-Agent": USER_AGENT,
        "Authorization": "Bearer " + key,
        "Accept": "application/json",
    }


def _request(method, url, key, **kwargs):
    """Single request with backoff on 429 and 5xx."""
    delay = 5
    for attempt in range(5):
        response = requests.request(method, url, headers=_headers(key), timeout=60, **kwargs)
        if response.status_code == 429 or response.status_code >= 500:
            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else delay
            print("    rate limited (HTTP " + str(response.status_code) + "), waiting " + str(wait) + "s")
            time.sleep(wait)
            delay = min(delay * 2, 120)
            continue
        response.raise_for_status()
        return response.json()
    raise UploadError("gave up after repeated rate limiting on " + url)


def _extract(result):
    data = result.get("skin", {}).get("texture", {}).get("data", {})
    value, signature = data.get("value"), data.get("signature")
    if not value or not signature:
        raise UploadError("response had no texture value/signature")
    return value, signature


def upload(path, name, variant="classic", key=None):
    """
    Uploads one PNG and returns (texture_value, signature).

    `name` is the skin's manifest key; MineSkin caps its own label at 20 chars.
    `variant` is 'classic' (Steve) or 'slim' (Alex) - it is baked into the signed
    texture, so it cannot be changed later without re-uploading.
    """
    if variant not in ("classic", "slim"):
        raise UploadError("unknown model variant: " + variant)
    key = key or api_key()

    with open(path, "rb") as handle:
        result = _request(
            "POST",
            BASE_URL + "/queue",
            key,
            files={"file": (path.name, handle, "image/png")},
            data={"variant": variant, "visibility": "unlisted", "name": name[:20]},
        )

    job_id = result.get("job", {}).get("id")
    if not job_id:
        # The queue can complete inline, in which case the POST already carries the skin.
        if result.get("skin"):
            return _extract(result)
        raise UploadError("no job id and no skin in the queue response")

    for _ in range(POLL_ATTEMPTS):
        status_result = _request("GET", BASE_URL + "/queue/" + job_id, key)
        status = status_result.get("job", {}).get("status", "")
        if status == "completed":
            return _extract(status_result)
        if status == "failed":
            raise UploadError("job failed: " + str(status_result.get("errors", "unknown")))
        time.sleep(POLL_INTERVAL)

    raise UploadError("job " + job_id + " did not complete within " + str(POLL_ATTEMPTS) + "s")
