# src/internet/search.py
#
# Web search via DuckDuckGo (keyless). Google/Bing are not scraped (they block
# it and need paid keys). This version LOGS LOUDLY with a [search] prefix: if
# the package fails to import, or a backend errors or returns nothing, the real
# reason is printed to the console, so a silent empty result can be diagnosed
# instead of guessed at.
import time

# Import diagnostics: if this fails, EVERY search silently returns nothing, so
# make the reason visible at startup rather than hiding it behind DDGS = None.
DDGS = None
_IMPORT_ERROR = None
try:
    from duckduckgo_search import DDGS as _DDGS
    DDGS = _DDGS
except Exception as _e:  # noqa: BLE001
    _IMPORT_ERROR = _e
    print(f"[search] FAILED to import duckduckgo_search: {type(_e).__name__}: {_e}")
    print("[search] Web search will not work until this import succeeds. "
          "Check that 'duckduckgo_search' is installed in the venv.")


class WebSearch:
    # Backends valid in duckduckgo_search 6.4.2: api (duckduckgo.com), html
    # (html.duckduckgo.com), lite (lite.duckduckgo.com). Any one can be
    # throttled at a given moment, so we try each and report what happened.
    _BACKENDS = ("api", "html", "lite")

    def __init__(self, retries: int = 2, pause_sec: float = 1.5):
        self.retries = retries
        self.pause_sec = pause_sec

    def search(self, query: str, max_results: int = 5) -> list:
        """Return a list of {title, url, snippet}. Never raises. Prints a
        [search] line for the query, each backend attempt, and the final
        outcome so failures are visible in the console."""
        query = (query or "").strip()
        if not query:
            print("[search] empty query; nothing to do")
            return []
        if DDGS is None:
            print(f"[search] cannot search: duckduckgo_search import failed "
                  f"earlier ({_IMPORT_ERROR!r})")
            return []

        print(f"[search] query={query!r} max_results={max_results}")
        last_err = None
        for attempt in range(self.retries + 1):
            for backend in self._BACKENDS:
                try:
                    rows = self._search_backend(query, max_results, backend)
                    if rows:
                        print(f"[search] backend={backend} attempt={attempt} "
                              f"-> {len(rows)} results")
                        return rows
                    print(f"[search] backend={backend} attempt={attempt} "
                          f"-> 0 results")
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

    def _search_backend(self, query: str, max_results: int, backend: str) -> list:
        out = []
        # DDGS is a context manager; a fresh instance per call avoids stale
        # sessions that can wedge after a rate-limit.
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
