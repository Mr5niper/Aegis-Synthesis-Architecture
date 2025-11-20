from duckduckgo_search import DDGS

class WebSearch:
    def __init__(self): self.ddg = DDGS()
    def search(self, query: str, max_results: int = 5):
        return [{"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")} for r in self.ddg.text(query, max_results=max_results)]