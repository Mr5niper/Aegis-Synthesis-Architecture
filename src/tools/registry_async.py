import json, asyncio
import os
from typing import Dict, Any, List, Callable, Optional
from ..internet.search import WebSearch
from ..internet.fetch import fetch_text, extract_relevant
from ..internet.cache import WebCache
from ..memory.vector_store import LiteVectorStore
from ..core.config import AppConfig
import ast, operator as op
# Note: CodeSandbox import is moved inside __init__ to support conditional registration

def _safe_eval(expr: str) -> float | int:
    allowed_ops = {
        ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
        ast.Mod: op.mod, ast.Pow: op.pow, ast.USub: op.neg, ast.UAdd: op.pos,
        ast.FloorDiv: op.floordiv,
    }
    def _eval(node):
        if isinstance(node, ast.Num): return node.n
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_ops:
            return allowed_ops[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_ops:
            return allowed_ops[type(node.op)](_eval(node.left), _eval(node.right))
        raise ValueError("disallowed expression")
    return _eval(ast.parse(expr, mode="eval").body)

class AsyncToolRegistry:
    def __init__(self, kb: LiteVectorStore, cfg: AppConfig, peer_client: Optional[object] = None):
        self.kb, self.cfg, self.peer_client = kb, cfg, peer_client
        self.cache = WebCache(cfg.paths.web_cache_db)
        self.searcher = WebSearch()
        self.tools: Dict[str, Callable[[Dict[str, Any]], asyncio.Future]] = {
            "now": self._now,
            "calc": self._calc,
            "none": self._none,
            "search_web": self._search_web if cfg.assistant.allow_web_search else self._blocked,
            "research_web": self._research_web if cfg.assistant.allow_web_search else self._blocked,
            "fetch_url": self._fetch_url if cfg.assistant.allow_web_search else self._blocked,
            "kb_add": self._kb_add,
            "kb_query": self._kb_query,
            "ingest_url": self._ingest_url if cfg.assistant.allow_web_search else self._blocked,
        }

        # Conditionally add code_exec
        if cfg.assistant.allow_code_exec and os.getenv("AEGIS_ENABLE_CODE_EXEC", "") == "1":
            from .sandbox import CodeSandbox
            self.sandbox = CodeSandbox()
            self.tools["code_exec"] = self._code_exec
        else:
            self.tools["code_exec"] = self._blocked_code_exec

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())

    # Tool names that reach out to the internet. Used by the agent to decide
    # when the one-time, per-session web-search consent gate applies.
    WEB_TOOLS = ("search_web", "research_web", "fetch_url", "ingest_url")

    def web_open(self) -> bool:
        """True when the 'Allow all sites' master switch is on, meaning web
        tools may read any page without asking. When False, only the domains in
        allow_domains are readable and the agent asks one-time consent."""
        return bool(self.cfg.assistant.allow_all_web)

    def consent_warning(self) -> str:
        """The message shown once per session before the first web search when
        'Allow all sites' is OFF. Explains what happens and the limitation."""
        allowed = ", ".join(self.cfg.assistant.allow_domains) or "(none listed)"
        return (
            "\n\n---\n"
            "To answer that, I can search the web with DuckDuckGo. Before I do, "
            "you should know:\n"
            "- Your search words are sent to DuckDuckGo (they leave this machine).\n"
            "- 'Allow all sites' is currently OFF, so I can only open and read "
            "pages from your allowed-domains list: " + allowed + ".\n"
            "- Results from other sites will show up in the search list but I "
            "will not be able to open them, so the answer may be limited.\n"
            "You can turn on 'Allow all sites' in the Web Access panel for full "
            "reading. Reply 'yes' to search now within the allowed list. I will "
            "only ask this once per session."
        )

    async def call(self, name: str, args: Dict[str, Any]) -> str:
        if name not in self.tools:
            return f"Error: unknown tool '{name}'"
        try:
            return await asyncio.wait_for(self.tools[name](args or {}), timeout=self.cfg.assistant.tool_timeout_sec)
        except asyncio.TimeoutError:
            return f"Error: tool '{name}' timed out"
        except Exception as e:
            return f"Error executing {name}: {e}"
    
    async def _code_exec(self, a):
        code = str(a.get("code", ""))
        if not code:
            return "Error: 'code' argument required."
        stdout, stderr, retcode = await self.sandbox.execute_python(code)
        out = [f"Return Code: {retcode}"]
        if stdout: out.append(f"STDOUT:\n{stdout}")
        if stderr: out.append(f"STDERR:\n{stderr}")
        return "\n".join(out).strip()

    async def _blocked_code_exec(self, _a):
        return "code_exec disabled by configuration. Set assistant.allow_code_exec: true and AEGIS_ENABLE_CODE_EXEC=1 to enable."

    async def _now(self, _a):
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def _calc(self, a):
        expr = str(a.get("expr",""))
        try:
            return str(_safe_eval(expr))
        except Exception as e:
            return f"Error: {e}"

    async def _search_web(self, a):
        q, k = str(a.get("query","")), int(a.get("k",5))
        res = await asyncio.get_event_loop().run_in_executor(None, self.searcher.search, q, k)
        return json.dumps(res, ensure_ascii=False)

    async def _research_web(self, a):
        """Full research loop in one call: search, then fetch and read the top
        results, returning a compact digest the model answers from.

        For each of the top results (honoring the domain allowlist), fetch the
        page, extract the passage most relevant to the query, and assemble a
        numbered, source-attributed digest. The model reads this and writes the
        answer with a citation. Pages blocked by the allowlist or that error out
        are still listed with their status, so the model can point the user to
        the page or explain why it could not be read."""
        q = str(a.get("query", ""))
        k = int(a.get("k", 4))
        if not q:
            return "Error: 'query' argument required."
        # 1. Search.
        results = await asyncio.get_event_loop().run_in_executor(None, self.searcher.search, q, max(k, 3))
        if not results:
            return ("No search results were returned (the search backend may be "
                    "temporarily rate-limited). Try rephrasing or ask again.")
        # 2. Fetch and distil the top results.
        loop = asyncio.get_event_loop()
        parts = []
        read_count = 0
        for i, r in enumerate(results[:k], 1):
            url = r.get("url", "")
            title = r.get("title", "") or url
            snippet = r.get("snippet", "") or ""
            page = ""
            if url:
                if cached := self.cache.get(url):
                    page = cached
                else:
                    page = await loop.run_in_executor(
                        None, fetch_text, url, "Aegis/1.0", self.cfg.assistant.allow_domains,
                        9000, self.cfg.assistant.allow_all_web)
                    if page and not page.startswith("[Blocked") and not page.startswith("[Error"):
                        self.cache.put(url, page)
            if page.startswith("[Blocked") or page.startswith("[Error"):
                # Could not read the page; give the model the search snippet and
                # the status so it can still point the user there.
                body = f"(could not read page: {page}) Search snippet: {snippet}"
            elif page:
                body = extract_relevant(page, q)
                read_count += 1
            else:
                body = f"Search snippet: {snippet}"
            parts.append(f"[{i}] {title}\nURL: {url}\n{body}")
        header = (f"Research for: {q}\nRead {read_count} of {len(results[:k])} top "
                  f"results. Use these sources to answer and cite the URL(s) you used.\n")
        return header + "\n\n".join(parts)

    async def _fetch_url(self, a):
        url = str(a.get("url",""))
        if cached := self.cache.get(url):
            return cached
        text = await asyncio.get_event_loop().run_in_executor(None, fetch_text, url, "Aegis/1.0", self.cfg.assistant.allow_domains, 9000, self.cfg.assistant.allow_all_web)
        self.cache.put(url, text)
        return text

    async def _kb_add(self, a):
        text = str(a.get("text","")); source = str(a.get("source","tool"))
        n = await asyncio.get_event_loop().run_in_executor(None, self.kb.add_document, text, source)
        return f"Added {n} chunks."

    async def _kb_query(self, a):
        q, k = str(a.get("query","")), int(a.get("k",3))
        return await asyncio.get_event_loop().run_in_executor(None, self.kb.retrieve_context, q, k)

    async def _ingest_url(self, a):
        url = str(a.get("url",""))
        text = self.cache.get(url)
        if not text:
            text = await self._fetch_url({"url": url})
            self.cache.put(url, text)
        n = await asyncio.get_event_loop().run_in_executor(None, self.kb.add_document, text, url)
        return f"Ingested {n} chunks from {url}"

    async def _blocked(self, _a):
        return "Access disabled by configuration."

    async def _none(self, _a):
        return ""