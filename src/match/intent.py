"""Extract budget and keywords from user natural language input."""
import re
from dataclasses import dataclass
from typing import List


@dataclass
class Intent:
    budget_min: float | None = None
    budget_max: float | None = None
    keywords: List[str] = None

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


# Common patterns for budget
BUDGET_PATTERNS = [
    r"(\$|USD|dollars?)\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
    r"under\s*(\$|USD)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
    r"below\s*(\$|USD)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
    r"(\d+)\s*-\s*(\d+)\s*(\$|USD|dollars?)",
    r"(\$|USD)?\s*(\d+)\s*to\s*(\$|USD)?\s*(\d+)",
    r"budget\s*(?:of)?\s*(\$|USD)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
    r"around\s*(\$|USD)?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
    r"(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(\$|USD)",
]


def _parse_number(s: str) -> float:
    return float(re.sub(r"[^\d.]", "", s.replace(",", "")))


def extract_intent(text: str) -> Intent:
    intent = Intent()
    t = (text or "").strip().lower()

    for pat in BUDGET_PATTERNS:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        g = m.groups()
        nums = [_parse_number(x) for x in g if x and re.match(r"[\d,\.]+", str(x))]
        if "under" in pat or "below" in pat:
            if nums:
                intent.budget_max = nums[0]
        elif "to" in pat and len(nums) >= 2:
            intent.budget_min = min(nums)
            intent.budget_max = max(nums)
        elif "-" in pat and len(nums) >= 2:
            intent.budget_min = min(nums)
            intent.budget_max = max(nums)
        elif nums:
            v = nums[0]
            if intent.budget_max is None and intent.budget_min is None:
                intent.budget_min = v * 0.7
                intent.budget_max = v * 1.3
        if intent.budget_min is not None or intent.budget_max is not None:
            break

    # Simple keyword extraction: remove stopwords, keep meaningful tokens
    STOP = {
        "a", "an", "the", "i", "me", "my", "want", "need", "looking", "for",
        "buy", "get", "find", "recommend", "suggest", "under", "over", "around",
        "best", "good", "nice", "please", "thanks", "thank", "you", "is", "are",
        "to", "in", "on", "at", "of", "and", "or", "with", "usd", "dollars",
    }
    words = re.findall(r"[a-z0-9]+", t)
    keywords = [w for w in words if len(w) >= 2 and w not in STOP]
    intent.keywords = list(dict.fromkeys(keywords))[:15]
    return intent
