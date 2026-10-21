import time
import random
import requests


def request_with_retry(method, url, key, max_tries=4, timeout=30, **kwargs):
    """Retry only on 429, 5xx and network errors. Never retry other 4xx."""
    for attempt in range(1, max_tries + 1):
        r = None
        try:
            r = requests.request(method, url, headers={"x-goog-api-key": key},
                                 timeout=timeout, **kwargs)
        except requests.RequestException as e:
            err = f"network error: {type(e).__name__}"
        else:
            if r.status_code != 429 and r.status_code < 500:
                return r
            err = f"HTTP {r.status_code}"
        if attempt == max_tries:
            raise RuntimeError(f"gave up after {max_tries} tries ({err})")
        wait = min(2 ** attempt, 30) + random.uniform(0, 1)
        ra = r.headers.get("Retry-After", "") if r is not None else ""
        if ra.isdigit():
            wait = max(wait, int(ra))
        print(f"  {err}, retrying in {wait:.1f}s")
        time.sleep(wait)