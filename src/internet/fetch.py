# src/internet/fetch.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse


def _domain_allowed(url: str, allow_domains: list, allow_all: bool = False) -> bool:
    if allow_all:
        return True  # master switch on: any site may be opened
    if not allow_domains:
        # No master switch and no list: nothing is allowed. (Allow-all is now an
        # explicit flag, not "empty list", so an empty list means "no sites".)
        return False
    dom = urlparse(url).netloc.lower()
    return any(dom == ad or dom.endswith("." + ad) or dom.endswith(ad) for ad in allow_domains)


def fetch_text(url: str, user_agent: str, allow_domains: list, max_chars: int = 9000, allow_all: bool = False) -> str:
    """Fetch a page and return cleaned visible text, or a bracketed status
    string starting with '[Blocked' or '[Error' that the model can relay to the
    user. Never raises for ordinary network/HTTP problems.

    allow_all is the master switch: when True, any site may be opened and the
    allow_domains list is ignored. When False, only allow_domains are opened."""
    dom = urlparse(url).netloc
    if not _domain_allowed(url, allow_domains, allow_all):
        return (f"[Blocked: '{dom}' is not in the allowed-domains list. Turn on "
                f"'Allow all sites' in Web Access, or add this domain, to read it.]")
    try:
        resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=12)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return f"[Error: timed out fetching {url}]"
    except requests.exceptions.HTTPError as e:
        return f"[Error: {getattr(e.response, 'status_code', 'HTTP')} fetching {url}]"
    except Exception as e:
        return f"[Error fetching {url}: {e}]"
    soup = BeautifulSoup(resp.text, "html.parser")
    for t in soup(["script", "style", "noscript", "nav", "footer", "aside"]):
        t.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:max_chars]


def extract_relevant(text: str, query: str, window: int = 600, max_chars: int = 1200) -> str:
    """Return the portion of `text` most relevant to `query`.

    A light, dependency-free heuristic: score fixed windows by how many query
    words they contain and return the best one (plus a little of the start for
    context). This is what lets the research loop hand the model the passage
    that actually answers the question instead of a whole page. If nothing
    matches, return the beginning of the text.
    """
    if not text or text.startswith("[Blocked") or text.startswith("[Error"):
        return text
    words = [w for w in "".join(c.lower() if c.isalnum() else " " for c in query).split() if len(w) > 2]
    if not words:
        return text[:max_chars]
    low = text.lower()
    best_i, best_score = 0, -1
    step = window // 2 or 1
    for i in range(0, max(1, len(text)), step):
        chunk = low[i:i + window]
        score = sum(chunk.count(w) for w in words)
        if score > best_score:
            best_score, best_i = score, i
    if best_score <= 0:
        return text[:max_chars]
    start = max(0, best_i - 100)
    snippet = text[start:best_i + window].strip()
    # Prepend a little of the page start for context if we jumped deep in.
    head = text[:200].strip()
    if start > 200 and head and head not in snippet:
        snippet = head + " ... " + snippet
    return snippet[:max_chars]
