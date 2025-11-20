from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Literal, List

ToolName = Literal[
    "search_web",
    "fetch_url",
    "kb_add",
    "kb_query",
    "ingest_url",
    "now",
    "calc",
    "code_exec", # Added for sandbox
    "none"
]

class ToolCall(BaseModel):
    tool: ToolName = "none"
    args: Dict[str, Any] = Field(default_factory=dict)
    rationale: Optional[str] = None

class SuggestionEvent(BaseModel):
    type: Literal["suggestion", "consent_request"] = "suggestion"
    text: str
    source: Literal["sentinel","curator", "system"] = "system"
    meta: Optional[Dict[str, Any]] = None
