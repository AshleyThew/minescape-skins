"""
MineSkin v2 client.

The API publishes this key's limits at /v2/me - for the key in use, 3s between
requests, 20 a minute and 100 an hour. This client reads them rather than assuming,
paces itself to stay inside them, and refuses to sit in CI waiting out an exhausted
hourly quota: a 429 asking for a long wait raises QuotaExhausted so the caller can keep
the uploads it already paid for and resume in a later run.
"""

import os
import time

import requests

BASE_URL = "https://api.mineskin.org/v2"
USER_AGENT = "MineScapeSkinUploader/2.0 (+https://github.com/AshleyThew/minescape-skins)"

# Used only when /v2/me cannot be read; deliberately conservative.
FALLBACK_GRANTS = {"delay": 3, "per_minute": 20, "per_hour": 100, "concurrency": 1}

# A 429 asking us to wait longer than this is an exhausted quota window, not request
# spacing. Waiting it out would burn most of an hour of CI for nothing.
MAX_WAIT = 120

POLL_INTERVAL = 2
POLL_ATTEMPTS = 60


class UploadError(Exception):
    """One skin could not be uploaded. Other skins may still succeed."""


class QuotaExhausted(Exception):
    """The API quota is spent. Stop, keep what succeeded, resume later."""

    def __init__(self, retry_after):
        super().__init__("MineSkin quota exhausted; retry in " + str(int(retry_after)) + "s")
        self.retry_after = retry_after


def api_key():
    key = os.getenv("MINESKIN_API_KEY") or os.getenv("API_KEY")
    if not key:
        raise UploadError("MINESKIN_API_KEY is not set")
    return key


def _headers(key):
    return {"User-Agent": USER_AGENT, "Authorization": "Bearer " + key, "Accept": "application/json"}


def get_grants(key):
    """This key's actual limits, so pacing follows the account rather than a guess."""
    try:
        r = requests.get(BASE_URL + "/me", headers=_headers(key), timeout=30)
        r.raise_for_status()
        grants = dict(FALLBACK_GRANTS)
        grants.update({k: v for k, v in (r.json().get("grants") or {}).items()
                       if isinstance(v, (int, float))})
        return grants
    except Exception:
        return dict(FALLBACK_GRANTS)


def _describe(response):
    """MineSkin puts the real reason in errors[]; without it a 400 is unreadable."""
    try:
        errors = response.json().get("errors") or []
        if errors:
            return "; ".join(str(e.get("code", "")) + ": " + str(e.get("message", "")) for e in errors)
    except Exception:
        pass
    return response.text[:200]


class Client:
    """Paces every request against the key's advertised limits."""

    def __init__(self, key=None):
        self.key = key or api_key()
        self.grants = get_grants(self.key)
        # Honour whichever is slower: the stated delay, or the per-minute allowance.
        # The margin keeps 20/minute off the exact boundary, which trips a 429.
        per_minute = max(float(self.grants.get("per_minute", 20)), 1)
        self.delay = max(float(self.grants.get("delay", 3)), 60.0 / per_minute) + 0.5
        self._next_allowed = 0.0

    @property
    def per_hour(self):
        return int(self.grants.get("per_hour", 100))

    def _wait_turn(self):
        now = time.monotonic()
        if now < self._next_allowed:
            time.sleep(self._next_allowed - now)

    def _note_rate_limit(self, response):
        """Honour whatever the response says about when we may go again."""
        wait = self.delay
        try:
            rl = response.json().get("rateLimit") or {}
            nxt = (rl.get("next") or {}).get("relative")
            if isinstance(nxt, (int, float)) and nxt > 0:
                wait = max(wait, nxt / 1000.0)
            millis = (rl.get("delay") or {}).get("millis")
            if isinstance(millis, (int, float)) and millis > 0:
                wait = max(wait, millis / 1000.0)
        except Exception:
            pass
        self._next_allowed = time.monotonic() + wait

    def request(self, method, url, **kwargs):
        attempts = 0
        while True:
            self._wait_turn()
            response = requests.request(method, url, headers=_headers(self.key), timeout=60, **kwargs)
            self._note_rate_limit(response)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else self.delay * 4
                if wait > MAX_WAIT:
                    raise QuotaExhausted(wait)
                attempts += 1
                if attempts > 5:
                    raise QuotaExhausted(wait)
                print("    rate limited, waiting " + str(int(wait)) + "s")
                time.sleep(wait)
                self._next_allowed = time.monotonic() + self.delay
                continue

            if response.status_code >= 500:
                attempts += 1
                if attempts > 4:
                    raise UploadError("server error " + str(response.status_code) + ": " + _describe(response))
                time.sleep(min(self.delay * (2 ** attempts), MAX_WAIT))
                continue

            if not response.ok:
                raise UploadError("HTTP " + str(response.status_code) + " - " + _describe(response))

            return response.json()

    def _extract(self, result):
        data = result.get("skin", {}).get("texture", {}).get("data", {})
        value, signature = data.get("value"), data.get("signature")
        if not value or not signature:
            raise UploadError("response had no texture value/signature")
        return value, signature

    def upload(self, path, name, variant="classic"):
        """
        Uploads one PNG and returns (texture_value, signature).

        `variant` is 'classic' (Steve) or 'slim' (Alex) - it is baked into the signed
        texture, so it cannot be changed later without re-uploading.
        """
        if variant not in ("classic", "slim"):
            raise UploadError("unknown model variant: " + variant)

        with open(path, "rb") as handle:
            result = self.request(
                "POST",
                BASE_URL + "/queue",
                files={"file": (path.name, handle, "image/png")},
                data={"variant": variant, "visibility": "unlisted", "name": name[:20]},
            )

        job_id = result.get("job", {}).get("id")
        if not job_id:
            # The queue can complete inline, in which case the POST already carries the skin.
            if result.get("skin"):
                return self._extract(result)
            raise UploadError("no job id and no skin in the queue response")

        for _ in range(POLL_ATTEMPTS):
            status_result = self.request("GET", BASE_URL + "/queue/" + job_id)
            status = status_result.get("job", {}).get("status", "")
            if status == "completed":
                return self._extract(status_result)
            if status == "failed":
                raise UploadError("job failed: " + str(status_result.get("errors", "unknown")))
            time.sleep(POLL_INTERVAL)

        raise UploadError("job " + job_id + " did not complete in time")
