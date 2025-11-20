# src/learning/style_adapter.py
from collections import Counter
import re
import json
from pathlib import Path

class StyleAdapter:
    """Learn and adapt to user's communication style"""
    
    def __init__(self, storage_path: str = "data/user_data/style_patterns.json"):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_patterns = self._load_patterns()
    def _load_patterns(self):
        """Load previously learned patterns"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path) as f:
                    data = json.load(f)
                # Convert Counter back from dict
                data["question_types"] = Counter(data.get("question_types", {}))
                return data
            except Exception:
                pass
        
        # Default patterns
        return {
            "avg_message_length": [],
            "question_types": Counter(),
            "formality_score": [],
            "emoji_usage": 0,
            "code_requests": 0,
            "total_messages": 0
        }   
        
    def save_patterns(self):
        """Persist learned patterns"""
        data = dict(self.user_patterns)
        # Convert Counter to dict for JSON serialization
        data["question_types"] = dict(data["question_types"])
        
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def analyze_message(self, text: str):
        """Extract patterns from user message"""
        self.user_patterns["total_messages"] += 1
        
        if len(text.split()) > 0:
            self.user_patterns["avg_message_length"].append(len(text.split()))
        
        text_lower = text.lower()
        if "how" in text_lower:
            self.user_patterns["question_types"]["how"] += 1
        if "why" in text_lower:
            self.user_patterns["question_types"]["why"] += 1
        if "what" in text_lower:
            self.user_patterns["question_types"]["what"] += 1
        
        formal_words = ["please", "could you", "would you", "kindly"]
        formality = sum(1 for w in formal_words if w in text_lower)
        self.user_patterns["formality_score"].append(formality)
        
        if any(char in text for char in "😀😃😄😁😆😅🤣😂"):
            self.user_patterns["emoji_usage"] += 1
        
        if "```" in text or "code" in text_lower or "function" in text_lower:
            self.user_patterns["code_requests"] += 1
        
        # Save every 10 messages
        if self.user_patterns["total_messages"] % 10 == 0:
            self.save_patterns()
    
    def get_adapted_prompt_prefix(self) -> str:
        """Generate system prompt modifications based on learned style"""
        if self.user_patterns["total_messages"] < 5 or not self.user_patterns["avg_message_length"]:
            return ""
        
        adaptations = []
        
        # Length preference
        avg_len = sum(self.user_patterns["avg_message_length"]) / len(self.user_patterns["avg_message_length"])
        if avg_len < 10:
            adaptations.append("User prefers brief messages. Be concise.")
        elif avg_len > 30:
            adaptations.append("User writes detailed messages. Provide thorough responses.")
        
        # Formality
        avg_formality = sum(self.user_patterns["formality_score"]) / len(self.user_patterns["formality_score"])
        if avg_formality > 0.5:
            adaptations.append("User is formal. Maintain professional tone.")
        else:
            adaptations.append("User is casual. Use conversational tone.")
        
        # Code interest
        code_ratio = self.user_patterns["code_requests"] / self.user_patterns["total_messages"]
        if code_ratio > 0.3:
            adaptations.append("User frequently requests code. Prioritize code examples.")
        
        return " ".join(adaptations)