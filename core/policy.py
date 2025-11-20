import time
from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class PolicyManager:
    allow_web_search: bool = True; proactive_enabled: bool = True
    allow_domains: List[str] = field(default_factory=list)
    quiet_hours: Tuple[int,int] = (23, 7); suggestions_per_min: int = 6
    _history: List[float] = field(default_factory=list, repr=False)

    def in_quiet_hours(self, now_local_hour: int) -> bool:
        a, b = self.quiet_hours
        return a <= now_local_hour < b if a <= b else now_local_hour >= a or now_local_hour < b

    def throttle_ok(self) -> bool:
        now = time.time()
        self._history = [t for t in self._history if now - t < 60]
        if len(self._history) >= self.suggestions_per_min: return False
        self._history.append(now); return True

    def domain_allowed(self, hostname: str) -> bool:
        return not self.allow_domains or any(hostname.endswith(d) or hostname == d for d in self.allow_domains)