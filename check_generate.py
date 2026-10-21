import json
import os
from pathlib import Path
from dotenv import load_dotenv
from http_util import request_with_retry

BASE = "https://generativelanguage.googleapis.com/v1beta/models"
LOG = Path("logs/gemini_generate.log")


def log_error(msg):
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main():
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("ERROR: GEMINI_API_KEY is missing from .env")
        return 1
    cfg = Path("llm_config.json")
    if not cfg.exists():
        print("ERROR: llm_config.json not found")
        return 1
    candidates = json.loads(cfg.read_text(encoding="utf-8"))["candidates"]

    body = {
        "contents": [{"parts": [{"text": "Reply with the single word: OK"}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 200},
    }
    ok = failed = 0
    for model in candidates:
        print(f"\n== {model}")
        try:
            r = request_with_retry("POST", f"{BASE}/{model}:generateContent",
                                   key, json=body)
        except RuntimeError as e:
            msg = str(e).replace(key, "[REDACTED]")
            log_error(f"{model}: {msg}")
            print("ERROR:", msg)
            failed += 1
            continue
        if r.status_code != 200:
            msg = r.text[:300].replace(key, "[REDACTED]")
            log_error(f"{model}: HTTP {r.status_code}: {msg}")
            print(f"ERROR: HTTP {r.status_code}\n{msg}")
            failed += 1
            continue
        try:
            data = r.json()
            cand = data["candidates"][0]
            text = "".join(p.get("text", "") for p in cand["content"]["parts"])
            usage = data["usageMetadata"]
        except (ValueError, KeyError, IndexError, TypeError):
            print("MISMATCH: answer shape is not what I expected")
            log_error(f"{model}: shape mismatch")
            failed += 1
            continue
        print("answer:", text.strip())
        print("finishReason:", cand.get("finishReason"))
        names = ("promptTokenCount", "candidatesTokenCount",
                 "thoughtsTokenCount", "totalTokenCount")
        print("tokens:", {k: usage.get(k) for k in names})
        ok += 1
    print(f"\nprocessed {len(candidates)} / succeeded {ok} / "
          f"failed {failed} / skipped 0")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())