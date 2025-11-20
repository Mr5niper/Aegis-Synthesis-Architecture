# src/core/user_profile.py
import json
from pathlib import Path
from typing import Dict, Any

class UserProfile:
    """Persistent user preferences and personalization"""
    
    def __init__(self, profile_path: str = "data/user_data/profile.json"):
        self.path = Path(profile_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
    
    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except json.JSONDecodeError:
                print(f"Warning: Could not decode {self.path}. Using default profile.")
                pass
        return {
            "name": "",
            "preferences": {
                "response_style": "balanced",  # concise, detailed, balanced
                "formality": "casual",  # formal, casual, technical
                "explanation_depth": "medium"  # shallow, medium, deep
            },
            "interests": [],
            "expertise": {},
            "communication_patterns": {
                "preferred_greeting": True,
                "emoji_usage": False,
                "code_preference": "python"
            }
        }
    
    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2))
    
    def get_system_prompt_addon(self) -> str:
        """Generate personalized system prompt addition"""
        prefs = self.data.get("preferences", {})
        parts = []
        
        if name := self.data.get("name"):
            parts.append(f"The user's name is {name}.")
        
        if style := prefs.get("response_style"):
            styles = {
                "concise": "Keep responses brief and to-the-point.",
                "detailed": "Provide comprehensive, detailed explanations.",
                "balanced": "Balance brevity with completeness."
            }
            parts.append(styles.get(style, ""))
        
        if interests := self.data.get("interests"):
            parts.append(f"User interests: {', '.join(interests)}.")
        
        return " ".join(parts)