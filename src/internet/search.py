# src/internet/search.py
#
# Web search via DuckDuckGo. DuckDuckGo is used because it has a keyless,
# widely-used text-search interface (the duckduckgo_search package). Google and
# Bing are intentionally NOT scraped here: they block automated scraping and
# require paid API keys to query reliably, so adding them would make search
# flaky rather than better. DuckDuckGo exposes several backends (api, html,
# lite); any one can be rate-limited at a given moment, so we try them in turn
# and retry briefly before giving up. Results are normalized to a common shape.
import time

try:
    from duckduckgo_search import DDGS
except Exception:  # pragma: no cover - import guard
    DDGS = None


class WebSearch:
    # Order matters: 'api' is richest, 'html'/'lite' are fallbacks that tend to
    # keep working when 'api' is throttled.
    _BACKENDS = ("api", "html", "lite")

    def __init__(self, retries: int = 2, pause_sec: float = 1.0):
        self.retries = retries
        self.pause_sec = pause_sec

    def search(self, query: str, max_results: int = 5) -> list:
        """Return a list of {title, url, snippet}. Never raises; on total
        failure returns an empty list so callers can report 'no results'
        rather than crash."""
        query = (query or "").strip()
        if not query or DDGS is None:
            return []

        last_err = None
        for attempt in range(self.retries + 1):
            for backend in self._BACKENDS:
                try:
                    rows = self._search_backend(query, max_results, backend)
                    if rows:
                        return rows
                except Exception as e:
                    last_err = e
                    continue
            # All backends failed this round; brief pause then retry.
            if attempt < self.retries:
                time.sleep(self.pause_sec)
        # Nothing worked. Return empty; the tool layer turns this into a
        # readable message that includes last_err if useful.
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
