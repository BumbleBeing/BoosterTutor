"""Downloading, with the etiquette rules built in rather than bolted on.

Scryfall and 17Lands ask for the same courtesies, and the development plan
(2.2, 2.3) makes them non-negotiable:
  * identify yourself in the User-Agent
  * cache to disk; never re-fetch what you already have
  * back off exponentially on failure; never retry in a tight loop

This is the only module in the ingest that touches the network. Ported from
DraftDouble's `fetching.py`, where it was proven against both upstreams.
"""

import datetime as dt
import email.utils
import gzip
import time
import urllib.error
import urllib.request
from pathlib import Path

from ..config import settings


class FetchError(RuntimeError):
    """Raised when a download fails after exhausting its retries."""


class UpstreamMissing(FetchError):
    """The file is not there (HTTP 403 or 404): an answer, not a failure.

    17Lands' S3 bucket answers 403 for a dump it has not published yet, so a
    set too new for data gets this rather than a network error.
    """


class HTTPStatusError(FetchError):
    """A 4xx answer, with its status and body, for callers that explain it.

    17Lands answers an unknown draft id with a 404 whose JSON body says why;
    the draft-link input shows that to the user (ADR 0023).
    """

    def __init__(self, url: str, status: int, body: bytes) -> None:
        super().__init__(f"{url} answered HTTP {status}")
        self.status = status
        self.body = body


def _http_error(url: str, exc: urllib.error.HTTPError) -> FetchError:
    if exc.code in (403, 404):
        return UpstreamMissing(f"{url} answered HTTP {exc.code}")
    return FetchError(f"{url} answered HTTP {exc.code}")


def _request(url: str) -> urllib.request.Request:
    # Both headers are required, not merely polite: api.scryfall.com answers a
    # request with no Accept header with a 400. urllib sends no Accept at all
    # by default (curl sends */*, which is why this only bites from Python).
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": settings.user_agent,
            "Accept": "application/json, */*;q=0.8",
        },
    )


def fetch_json_bytes(url: str, *, max_attempts: int = 4, timeout: float = 60) -> bytes:
    """Fetch a small JSON document into memory, with back-off.

    A 4xx answer is raised at once, as `HTTPStatusError`: the request itself
    was wrong, and asking again cannot change that.
    """
    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(_request(url), timeout=timeout) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                raise HTTPStatusError(url, exc.code, exc.read()) from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt < max_attempts:
            time.sleep(delay)
            delay *= 2  # exponential back-off, never a tight loop
    raise FetchError(
        f"failed to fetch {url} after {max_attempts} attempts: {last_error}"
    )


def fetch_to_file(
    url: str, dest: Path, *, force: bool = False, max_attempts: int = 4
) -> Path:
    """Download `url` to `dest`, or reuse `dest` if it is already there.

    Re-running an ingest in an afternoon of development must not re-download
    a 78 MB file each time; pass `force=True` for a fresh copy.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        return dest

    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(_request(url), timeout=120) as response:
                # Write to a temporary name first, so an interrupted download
                # can never be mistaken for a complete one on the next run.
                partial = dest.with_suffix(dest.suffix + ".partial")
                with partial.open("wb") as handle:
                    while chunk := response.read(1 << 20):
                        handle.write(chunk)
                partial.replace(dest)
                return dest
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt < max_attempts:
            time.sleep(delay)
            delay *= 2
    raise FetchError(
        f"failed to fetch {url} after {max_attempts} attempts: {last_error}"
    )


def fetch_gzip_first_line(url: str) -> str:
    """The first line of a gzipped text file, without downloading the rest.

    A 17Lands draft dump is tens of megabytes, but its header (one line, every
    column name) is all that is needed to know which cards were in its packs.
    The connection is closed after that line, so only the first few kilobytes
    cross the network. A missing file (a set too new for a dump) raises
    FetchError like any other 4xx.
    """
    try:
        with (
            urllib.request.urlopen(_request(url), timeout=60) as response,
            gzip.GzipFile(fileobj=response) as unzipped,
        ):
            return unzipped.readline().decode("utf-8").rstrip("\r\n")
    except urllib.error.HTTPError as exc:
        raise _http_error(url, exc) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"failed to fetch {url}: {exc}") from exc


def fetch_last_modified(url: str) -> dt.datetime | None:
    """When upstream last changed a file, from a HEAD request's Last-Modified.

    Cheap (no body), and it is what lets an ingest skip a large download when
    the file has not changed since its last run.
    """
    request = _request(url)
    request.method = "HEAD"
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            header = response.headers.get("Last-Modified")
    except urllib.error.HTTPError as exc:
        raise _http_error(url, exc) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"failed to reach {url}: {exc}") from exc
    return email.utils.parsedate_to_datetime(header) if header else None
