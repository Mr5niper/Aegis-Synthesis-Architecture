import json, asyncio
import os
from typing import Dict, Any, List, Callable, Optional
from ..internet.search import WebSearch
from ..internet.fetch import fetch_text
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

    async def _fetch_url(self, a):
        url = str(a.get("url",""))
        if cached := self.cache.get(url):
            return cached
        text = await asyncio.get_event_loop().run_in_executor(None, fetch_text, url, "Aegis/1.0", self.cfg.assistant.allow_domains)
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