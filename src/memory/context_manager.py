# src/memory/context_manager.py
from typing import List, Tuple
from dataclasses import dataclass
import time

@dataclass
class Message:
    role: str  # user or assistant
    content: str
    tokens: int
    timestamp: float

class ContextWindow:
    """Smart context window management with summarization"""
    
    def __init__(self, max_tokens: int = 3000):
        self.max_tokens = max_tokens
        self.messages: List[Message] = []
    
    def add_message(self, role: str, content: str):
        # Rough token estimate (will vary by tokenizer)
        # Assuming rough 1.3 word-to-token ratio, then split on spaces.
        tokens = len(content.split()) * 1.3 
        self.messages.append(Message(role, content, int(tokens), time.time()))
        self._maybe_compress()
    
    def _maybe_compress(self):
        """Compress old messages when approaching token limit"""
        if not self.messages:
            return
            
        total_tokens = sum(m.tokens for m in self.messages)
        
        if total_tokens > self.max_tokens * 0.8:
            # Ensure we have enough messages to summarize
            if len(self.messages) < 7:
                return

            recent = self.messages[-6:]
            to_summarize = self.messages[:-6]
            
            if to_summarize:
                summary_text = self._create_summary(to_summarize)
                summary_msg = Message(
                    "system",
                    f"[Previous conversation summary: {summary_text}]",
                    int(len(summary_text.split()) * 1.3),  # Make consistent with token calc
                    to_summarize[0].timestamp
                )
                self.messages = [summary_msg] + recent
    
    def _create_summary(self, messages: List[Message]) -> str:
        """Create summary of old messages (could use LLM for better results)"""
        topics = []
        for m in messages:
            if m.role == "user":
                # Extract key phrases (simple heuristic)
                words = m.content.split()
                if len(words) > 3:
                    topics.append(" ".join(words[:5]) + "...")
        return f"Discussed: {'; '.join(topics[:3])}"
    
    def get_context(self) -> str:
        """Get formatted context for prompt"""
        return "\n\n".join([
            f"{m.role.title()}: {m.content}"
            for m in self.messages
        ])