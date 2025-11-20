import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

def fetch_text(url: str, user_agent: str, allow_domains: list[str], max_chars: int = 9000) -> str:
    dom = urlparse(url).netloc
    if allow_domains and not any(dom.endswith(ad) or dom == ad for ad in allow_domains):
        return f"[Blocked: domain '{dom}' not in allowlist]"
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for t in soup(["script","style","noscript","nav","footer","aside"]): t.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:max_chars]