"""Madrid sweep "Fast mode" — rate-aware concurrency paced to WIPO's published
X-RateLimit budget. See docs/superpowers/specs/2026-06-23-madrid-fast-mode-design.md."""

from .controller import CEILING, FLOOR, START, Decision, RateWindow, next_concurrency

__all__ = ["CEILING", "FLOOR", "START", "Decision", "RateWindow", "next_concurrency"]
