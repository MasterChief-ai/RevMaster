import os, time, random
from pathlib import Path
import requests
from dotenv import load_dotenv

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT = 15
MAX_TRIES = 4
LOG = Path("logs/gemini_check.log")


def log_error(msg):
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def get_with_retry(url, key, params):
    for attempt in range(1, MAX_TRIES + 1):
        r = None
        try:
            r = requests.get(url, headers={"x-goog-api-key": key},
                             params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            err = f"network error: {type(e).__name__}"
        else:
            if r.status_code == 429 or r.status_code >= 500:
                err = f"HTTP {r.status_code}"
            else:
                return r  # success, or a 4xx: never retry 4xx
        if attempt == MAX_TRIES:
            raise RuntimeError(f"gave up after {MAX_TRIES} tries ({err})")
        wait = min(2 ** attempt, 30) + random.uniform(0, 1)
        if r is not None and r.headers.get("Retry-After", "").isdigit():
            wait = max(wait, int(r.headers["Retry-After"]))
        print(f"  {err}, retrying in {wait:.1f}s")
        time.sleep(wait)


def main():
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("ERROR: GEMINI_API_KEY is missing from .env")
        return 1

    models, token = [], None
    try:
        for _ in range(5):  # at most 5 pages
            params = {"pageSize": 100}
            if token:
                params["pageToken"] = token
            r = get_with_retry(BASE_URL, key, params)
            if r.status_code != 200:
                msg = r.text[:300].replace(key, "[REDACTED]")
                log_error(f"HTTP {r.status_code}: {msg}")
                print(f"ERROR: HTTP {r.status_code}\n{msg}")
                print("processed 1 / succeeded 0 / failed 1 / skipped 0")
                return 1
            data = r.json()
            if not isinstance(data.get("models"), list):
                print("MISMATCH: answer has no 'models' list")
                print("processed 1 / succeeded 0 / failed 1 / skipped 0")
                return 1
            models += data["models"]
            token = data.get("nextPageToken")
            if not token:
                break
    except (RuntimeError, ValueError) as e:
        msg = str(e).replace(key, "[REDACTED]")
        log_error(msg)
        print("ERROR:", msg)
        print("processed 1 / succeeded 0 / failed 1 / skipped 0")
        return 1

    usable = sorted(
        m.get("name", "?") for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    )
    print("HTTP 200 OK")
    print(f"Models returned: {len(models)}")
    print(f"Models that support generateContent: {len(usable)}")
    for name in usable:
        print("  ", name)
    print("Tokens used: 0 (no model was called)")
    print("processed 1 / succeeded 1 / failed 0 / skipped 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())