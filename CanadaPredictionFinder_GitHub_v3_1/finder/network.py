"""Read-only, allowlisted HTTPS client. No account credentials and no order routes."""
from __future__ import annotations
import json
import random
import re
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

BASE = "https://external-api.kalshi.com/trade-api/v2/"
SAFE_PATH = re.compile(r"(?:series(?:/[A-Za-z0-9._-]+)?|markets(?:/[A-Za-z0-9._-]+(?:/orderbook)?)?)\Z")
MAX_BYTES = 8_000_000


class SourceError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SourceError("Redirect refused; review source configuration before proceeding")


class PublicClient:
    def __init__(self, timeout: float = 8, requests_per_second: float = 2):
        self.timeout, self.spacing = timeout, 1/requests_per_second
        self.next_request = 0.0
        self.blocked_until = 0.0
        self.failures = 0
        self.opener = build_opener(NoRedirect())
        self.last_error = ""

    def get(self, path: str, params: dict | None = None) -> dict:
        if not SAFE_PATH.fullmatch(path):
            raise SourceError("Only allowlisted public market-data GET routes are permitted")
        now=time.monotonic()
        if now < self.blocked_until:
            raise SourceError("Source backoff active; no new request sent")
        time.sleep(max(0,self.next_request-now))
        self.next_request=time.monotonic()+self.spacing
        url=BASE+path+("?"+urlencode(params) if params else "")
        req=Request(url, method="GET", headers={"User-Agent":"CanadaPredictionFinder/3.0 (public-read-only)",
                    "Accept":"application/json", "Cache-Control":"no-cache"})
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                age=r.headers.get("Age", "0")
                if float(age)>30:
                    raise SourceError("Cached source response is too old")
                data=r.read(MAX_BYTES+1)
                if len(data)>MAX_BYTES:
                    raise SourceError("Source response exceeded size limit")
                result=json.loads(data)
                if not isinstance(result,dict):
                    raise SourceError("Unexpected response schema")
            self.failures=0
            self.last_error=""
            return result
        except HTTPError as exc:
            self.failures+=1
            if exc.code in {401,403,451}:
                delay=3600
                message=f"HTTP {exc.code}: access denied. No bypass; retry held for one hour."
            elif exc.code==429:
                delay=60
                retry=exc.headers.get("Retry-After","")
                try:
                    delay=max(delay,float(retry))
                except ValueError:
                    try:
                        dt=parsedate_to_datetime(retry)
                        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                        delay=max(delay,dt.timestamp()-time.time())
                    except (ValueError,TypeError,OverflowError):
                        pass
                delay=max(1,delay)+random.uniform(0,3)
                message="HTTP 429: source rate limit; Retry-After respected."
            elif exc.code==404:
                raise SourceError("HTTP 404: market/series not found") from exc
            else:
                delay=min(900,15*2**min(self.failures,6))
                message=f"HTTP {exc.code}: source unavailable"
            self.blocked_until=time.monotonic()+delay
            self.last_error=message
            raise SourceError(message) from exc
        except (URLError,TimeoutError,OSError,ValueError,SourceError) as exc:
            self.failures+=1
            self.blocked_until=time.monotonic()+min(900,15*2**min(self.failures,6))
            self.last_error=f"Read-only source failed: {type(exc).__name__}: {str(exc)[:200]}"
            raise SourceError(self.last_error) from exc
