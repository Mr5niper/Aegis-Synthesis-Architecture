# src/internet/search.py
#
# Web search with a selectable provider. Two are built in:
#   - "duckduckgo": keyless (duckduckgo_search package). Works with no setup but
#     is frequently rate-limited (HTTP 202) for automated queries.
#   - "tavily": Tavily API (https://tavily.com). Works in TWO modes:
#       * keyless (no key set): uses Tavily's public keyless access, which needs
#         no signup but is rate-limited. Supports search only.
#       * keyed (an API key set): higher limits; free tier ~1000 searches/month.
#     The keyless request is the same wire protocol the official tavily-python
#     SDK uses: no Authorization header, plus X-Tavily-Access-Mode: keyless and
#     X-Client-Source: tavily-python-keyless. A rate-limit comes back as a
#     recoverable-error envelope {"error": {"code", "message",
#     "retry_after_seconds", ...}} which we surface to the console.
# Only ONE provider is used per call (chosen in the Web Access panel); there is
# no silent cross-provider fallback, so a failure is reported honestly rather
# than masked by trying the other one. Adding another provider is a matter of
# writing a _search_<name> method and routing to it in search().
#
# All paths LOG with a [search] prefix so an empty result can be diagnosed
# (rate-limit, missing key, network error) instead of guessed at.
import time
import json as _json
import urllib.request as _urlreq
import urllib.error as _urlerr

# DuckDuckGo import diagnostics: if this fails, keyless search silently returns
# nothing, so make the reason visible rather than hiding it behind DDGS = None.
DDGS = None
_IMPORT_ERROR = None
try:
    from duckduckgo_search import DDGS as _DDGS
    DDGS = _DDGS
except Exception as _e:  # noqa: BLE001
    _IMPORT_ERROR = _e
    print(f"[search] FAILED to import duckduckgo_search: {type(_e).__name__}: {_e}")
    print("[search] Keyless DuckDuckGo search will not work until this import "
          "succeeds. Check that 'duckduckgo_search' is installed in the venv.")

_TAVILY_URL = "https://api.tavily.com/search"


def _tavily_is_error_envelope(body) -> bool:
    """True when a Tavily response body is the recoverable-error envelope shape
    {"error": {"code": <str>, ...}} (used for keyless rate-limit rejections)."""
    return (
        isinstance(body, dict)
        and isinstance(body.get("error"), dict)
        and isinstance(body["error"].get("code"), str)
    )


def _tavily_print_envelope(body) -> None:
    """Print the human-readable reason and retry hint from an error envelope."""
    err = body.get("error", {})
    msg = err.get("message") or "(no message)"
    ra = err.get("retry_after_seconds")
    extra = f" retry_after={ra}s" if ra is not None else ""
    print(f"[search] tavily keyless limit reached: {msg}{extra} "
          f"(add a free Tavily API key in the Web Access panel for higher limits)")


class WebSearch:
    # DuckDuckGo backends valid in duckduckgo_search 6.4.2: api, html, lite.
    _BACKENDS = ("api", "html", "lite")

    def __init__(self, retries: int = 2, pause_sec: float = 1.5):
        self.retries = retries
        self.pause_sec = pause_sec

    def search(self, query: str, max_results: int = 5,
               provider: str = "duckduckgo", tavily_api_key: str = "") -> list:
        """Return a list of {title, url, snippet}. Never raises. Routes to the
        selected provider and prints [search] lines describing what happened.

        No cross-provider fallback: if the selected provider fails, we return []
        (the caller degrades to a local answer and says the web was unreachable).
        """
        query = (query or "").strip()
        if not query:
            print("[search] empty query; nothing to do")
            return []

        prov = (provider or "duckduckgo").strip().lower()
        if prov == "tavily":
            # Empty key is allowed: Tavily supports a keyless (rate-limited)
            # mode that needs no signup. A key raises the limits.
            return self._search_tavily(query, max_results, (tavily_api_key or "").strip())

        # Default / "duckduckgo".
        return self._search_duckduckgo(query, max_results)

    # ---- Tavily -----------------------------------------------------------
    def _search_tavily(self, query: str, max_results: int, api_key: str) -> list:
        """Query the Tavily REST API using only the stdlib (urllib), so no extra
        dependency is required. Endpoint/shape per Tavily's API: POST
        https://api.tavily.com/search, JSON body, each result has
        title/url/content.

        With a key: Bearer auth. Without a key: keyless mode, replicating the
        official SDK's request (no Authorization; X-Tavily-Access-Mode: keyless
        and X-Client-Source: tavily-python-keyless). Keyless is rate-limited; a
        limit rejection arrives as an {"error": {...}} envelope which we report.
        """
        keyless = not api_key
        mode = "keyless" if keyless else "keyed"
        print(f"[search] provider=tavily ({mode}) query={query!r} max_results={max_results}")
        body = _json.dumps({
            "query": query,
            "max_results": max(1, int(max_results)),
            "search_depth": "basic",
        }).encode("utf-8")
        req = _urlreq.Request(_TAVILY_URL, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if keyless:
            req.add_header("X-Tavily-Access-Mode", "keyless")
            req.add_header("X-Client-Source", "tavily-python-keyless")
        else:
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("X-Client-Source", "tavily-python")
        try:
            with _urlreq.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", "replace")
            data = _json.loads(raw)
            # Defensive: a 200 that still carries the recoverable-error envelope.
            if _tavily_is_error_envelope(data):
                _tavily_print_envelope(data)
                return []
        except _urlerr.HTTPError as e:
            detail = ""
            body_obj = None
            try:
                detail = e.read().decode("utf-8", "replace")
                body_obj = _json.loads(detail)
            except Exception:  # noqa: BLE001
                body_obj = None
            # Keyless rate-limit (or other recoverable) error envelope.
            if _tavily_is_error_envelope(body_obj):
                _tavily_print_envelope(body_obj)
                return []
            print(f"[search] tavily HTTP {e.code} {e.reason}: {detail[:200]}")
            if e.code in (401, 403):
                print("[search] tavily rejected the API key. Check it in the Web "
                      "Access panel, or clear it to use keyless mode.")
            elif e.code == 429:
                print("[search] tavily rate/credit limit hit (429).")
            return []
        except Exception as e:  # noqa: BLE001
            print(f"[search] tavily ERROR {type(e).__name__}: {e}")
            return []

        rows = []
        for r in (data.get("results") or []):
            rows.append({
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "snippet": r.get("content") or "",
            })
            if len(rows) >= max_results:
                break
        print(f"[search] tavily ({mode}) -> {len(rows)} results")
        return rows

    # ---- DuckDuckGo -------------------------------------------------------
    def _search_duckduckgo(self, query: str, max_results: int) -> list:
        if DDGS is None:
            print(f"[search] cannot search: duckduckgo_search import failed "
                  f"earlier ({_IMPORT_ERROR!r})")
            return []
        print(f"[search] provider=duckduckgo query={query!r} max_results={max_results}")
        last_err = None
        for attempt in range(self.retries + 1):
            for backend in self._BACKENDS:
                try:
                    rows = self._ddg_backend(query, max_results, backend)
                    if rows:
                        print(f"[search] backend={backend} attempt={attempt} "
                              f"-> {len(rows)} results")
                        return rows
                    print(f"[search] backend={backend} attempt={attempt} -> 0 results")
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    print(f"[search] backend={backend} attempt={attempt} "
                          f"ERROR {type(e).__name__}: {e}")
                    continue
            if attempt < self.retries:
                print(f"[search] all backends failed round {attempt}; "
                      f"pausing {self.pause_sec}s then retrying")
                time.sleep(self.pause_sec)
        print(f"[search] GAVE UP after {self.retries + 1} rounds. "
              f"last_error={last_err!r}")
        return []

    def _ddg_backend(self, query: str, max_results: int, backend: str) -> list:
        out = []
        with DDGS() as ddg:
            for r in ddg.text(query, max_results=max_results, backend=backend):
                out.append({
                    "title": r.get("title") or "",
                    "url": r.get("href") or r.get("url") or "",
                    "snippet": r.get("body") or r.get("snippet") or "",
                })
                if len(out) >= max_results:
                    break
        return out
