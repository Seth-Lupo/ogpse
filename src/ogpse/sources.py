import csv
import fcntl
import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import DATA, ROOT

MANIFEST = DATA / "manifest.csv"
FIELDS = ["file", "url", "retrieved_utc", "bytes", "sha256"]
_SECRET_PARAMS = {"api_key"}
# Some public hosts (TxGIO CloudFront) reject non-browser user agents.
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"}


def _record(dest: Path, url: str):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _write_row(dest, url)


def _write_row(dest: Path, url: str):
    rows = []
    if MANIFEST.exists():
        with open(MANIFEST) as f:
            rows = [r for r in csv.DictReader(f) if r["file"] != str(dest.relative_to(ROOT))]
    rows.append({
        "file": str(dest.relative_to(ROOT)),
        "url": url,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": dest.stat().st_size,
        "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
    })
    rows.sort(key=lambda r: r["file"])
    with open(MANIFEST, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)


def public_url(url: str, params: dict | None) -> str:
    if not params:
        return url
    shown = {k: v for k, v in params.items() if k not in _SECRET_PARAMS and k != "email"}
    return requests.Request("GET", url, params=shown).prepare().url


def fetch(url: str, dest: Path, params: dict | None = None, method: str = "GET",
          retries: int = 6, timeout: int = 300) -> Path:
    """Download once, cache forever, and log provenance in data/manifest.csv."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            r = requests.request(method, url, params=params if method == "GET" else None,
                                 data=params if method == "POST" else None, headers=HEADERS, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code}")
            r.raise_for_status()
            break
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout):
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 3)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(r.content)
    os.replace(tmp, dest)
    _record(dest, public_url(url, params))
    return dest
