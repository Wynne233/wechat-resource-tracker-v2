from __future__ import annotations

import re
import uuid
from datetime import datetime


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now() -> datetime:
    return datetime.utcnow()


def normalize_name(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    return value


def canonical_key(value: str) -> str:
    return re.sub(r"[\s_\-\.]+", "", value.strip().lower())


def trust_weight(level: str) -> float:
    return {
        "high": 1.0,
        "medium": 0.7,
        "low": 0.4,
        "pending": 0.6,
        "blacklist": 0.0,
    }.get(level, 0.6)


def mask_webhook(url: str) -> str:
    if not url:
        return ""
    if len(url) <= 18:
        return "***"
    return f"{url[:12]}...{url[-8:]}"

