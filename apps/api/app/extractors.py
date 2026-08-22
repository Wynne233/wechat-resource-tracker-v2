from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schemas import StandardArticle
from .utils import normalize_name


def _load_local_env() -> None:
    root = Path(__file__).resolve().parents[3]
    for env_file in [root / ".env", root / "apps" / "api" / ".env"]:
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or "=" not in clean:
                continue
            key, value = clean.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()


EXTRACTION_VERSION = "mvp-hybrid-v2"
MAX_LLM_TEXT_CHARS = 9000


@dataclass
class ExtractedResource:
    name: str
    resource_type: str
    summary: str
    aliases: list[str] = field(default_factory=list)
    capability_tags: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    evidence_snippet: str = ""
    confidence: float = 0.72
    risk_level: str = "low"
    risk_notes: str = ""


RESOURCE_HINTS = [
    "\u5de5\u5177",
    "\u8f6f\u4ef6",
    "App",
    "APP",
    "\u5e94\u7528",
    "\u63d2\u4ef6",
    "\u7f51\u7ad9",
    "\u5e73\u53f0",
    "\u9879\u76ee",
    "\u5f00\u6e90",
    "\u542c\u6b4c",
    "\u8ffd\u5267",
    "\u9605\u8bfb",
    "\u6587\u6863",
    "\u56fe\u7247",
    "\u6548\u7387",
    "\u97f3\u4e50",
    "\u4e0b\u8f7d",
    "\u795e\u5668",
    "AI",
    "API",
    "PDF",
    "宸ュ叿",
    "杞欢",
    "寮€婧",
    "闊充箰",
    "涓嬭浇",
    "鍚瓕",
    "绁炲櫒",
]

PLATFORM_HINTS = ["Windows", "macOS", "iOS", "Android", "Web", "Linux"]
GENERIC_NAMES = {
    "AI",
    "API",
    "HTTP",
    "PDF",
    "App",
    "APP",
    "Web",
    "Windows",
    "Android",
    "macOS",
    "iOS",
    "PC",
    "Bilibili",
    "GitHub",
    "Linux",
    "RSS",
    "Postman",
    "\u97f3\u4e50",
    "\u542c\u6b4c",
    "\u514d\u8d39\u542c\u6b4c",
    "\u66f4\u65b0",
    "\u4e0b\u8f7d",
    "\u795e\u5668",
    "\u8f6f\u4ef6",
    "\u5de5\u5177",
    "\u52a9\u624b",
    "\u5e94\u7528",
    "\u8d44\u6e90",
    "\u7f51\u7ad9",
    "\u5e73\u53f0",
    "\u9879\u76ee",
    "\u5b98\u7f51",
    "\u5b98\u65b9\u7f51\u7ad9",
    "\u4e0b\u8f7d\u5730\u5740",
    "\u94fe\u63a5",
    "\u539f\u6587\u94fe\u63a5",
    "\u6f14\u793a",
    "\u5408\u96c6",
    "\u6574\u7406",
}

TITLE_NOISE = [
    "\u5408\u96c6",
    "\u63a8\u8350",
    "\u6e05\u5355",
    "\u6574\u7406",
    "\u5927\u5168",
    "\u9879\u76ee",
    "\u5de5\u5177",
]

INVALID_NAME_PARTS = [
    "\u5927\u5bb6\u597d",
    "\u4eca\u5929\u7ed9\u5927\u5bb6",
    "\u4e24\u6b3e",
    "\u4ec5\u652f\u6301",
    "\u4e0d\u8fc7\u8f6f\u4ef6",
    "\u5f00\u5c4f\u5e7f\u544a",
    "\u5012\u4e0b\u4e86",
    "澶у",
    "浠婂ぉ",
    "涓ゆ",
    "浠呮敮",
    "涓嶈繃",
    "寮€灞",
    "Part.",
    "鍊掍笅",
]


def detect_content_status(article: StandardArticle) -> str:
    content = _normalize_space(article.content_text)
    if len(content) >= 120:
        return "full_text"
    if content:
        return "partial_text"
    if article.title.strip():
        return "title_only"
    return "missing_content"


def extract_resources(article: StandardArticle) -> list[ExtractedResource]:
    status = detect_content_status(article)
    if status in {"title_only", "missing_content"}:
        return []
    candidates = _rule_extract(article, status)
    if status == "full_text":
        llm_items = _llm_extract(article, candidates)
        if llm_items:
            return _dedupe_resources(llm_items, article)
    return _dedupe_resources(candidates, article)


def _rule_extract(article: StandardArticle, content_status: str) -> list[ExtractedResource]:
    body = article.content_text.strip()
    if not body:
        return []

    resources: list[ExtractedResource] = []
    for sentence in _sentences(body):
        if not _resource_like(sentence):
            continue
        links = _links(sentence)
        for name in _candidate_names(sentence):
            resources.append(_make_resource(name, sentence[:280], article, content_status, links))
    return resources


def _make_resource(
    name: str,
    evidence: str,
    article: StandardArticle,
    content_status: str,
    links: list[str],
) -> ExtractedResource:
    text = f"{article.title}\n{article.content_text}\n{evidence}"
    platforms = [p for p in PLATFORM_HINTS if p.lower() in text.lower()]
    tags = _infer_tags(text)
    risk_level = "medium" if _has_risk_signal(text) else "low"
    confidence = 0.88 if links and content_status == "full_text" else 0.78
    return ExtractedResource(
        name=normalize_name(name),
        resource_type=_guess_type(text),
        summary=_summary_for(evidence, name, tags),
        capability_tags=tags,
        platforms=platforms,
        links=links,
        evidence_snippet=evidence,
        confidence=confidence,
        risk_level=risk_level,
        risk_notes="\u6587\u7ae0\u4e2d\u51fa\u73b0\u4e0d\u7a33\u5b9a\u3001\u505c\u6b62\u7ef4\u62a4\u6216\u98ce\u9669\u7ebf\u7d22\u3002" if risk_level != "low" else "",
    )


def _llm_extract(article: StandardArticle, candidates: list[ExtractedResource]) -> list[ExtractedResource]:
    api_key = os.getenv("RESOURCE_EXTRACTOR_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    enabled = os.getenv("RESOURCE_EXTRACTOR_LLM_ENABLED", "auto").lower()
    if enabled in {"0", "false", "off", "no"} or not api_key:
        return []

    payload = {
        "model": os.getenv("RESOURCE_EXTRACTOR_MODEL") or ("deepseek-chat" if os.getenv("DEEPSEEK_API_KEY") else "gpt-4o-mini"),
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract concrete resource entities from Chinese WeChat articles. "
                    "Resources must be named apps, websites, plugins, open-source projects, datasets, courses, services, or tools. "
                    "Do not output titles, categories, feature words, marketing phrases, or generic nouns. Return strict JSON only."
                ),
            },
            {"role": "user", "content": _llm_prompt(article, candidates)},
        ],
    }
    request = urllib.request.Request(
        _chat_completions_endpoint(),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            raw = json.loads(response.read().decode("utf-8"))
        parsed = json.loads(raw.get("choices", [{}])[0].get("message", {}).get("content", "{}"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, KeyError):
        return []

    resources: list[ExtractedResource] = []
    for item in parsed.get("resources", []):
        resource = _resource_from_llm_item(item)
        if resource and _valid_resource_name(resource.name, article, resource.evidence_snippet):
            resources.append(resource)
    return resources


def _chat_completions_endpoint() -> str:
    configured = os.getenv("RESOURCE_EXTRACTOR_BASE_URL", "").strip().rstrip("/")
    if configured:
        if configured.endswith("/chat/completions"):
            return configured
        return f"{configured}/chat/completions"
    if os.getenv("DEEPSEEK_API_KEY"):
        return "https://api.deepseek.com/chat/completions"
    return "https://api.openai.com/v1/chat/completions"


def _llm_prompt(article: StandardArticle, candidates: list[ExtractedResource]) -> str:
    candidate_payload = [
        {"name": item.name, "evidence": item.evidence_snippet, "tags": item.capability_tags, "links": item.links}
        for item in candidates[:16]
    ]
    schema = {
        "resources": [
            {
                "name": "Notion AI",
                "aliases": [],
                "type": "tool",
                "capability_tags": ["AI productivity", "knowledge base"],
                "summary": "One sentence describing the concrete resource.",
                "links": ["https://example.com"],
                "evidence_snippet": "Original article evidence.",
                "confidence": 0.86,
                "risk_level": "low",
                "risk_notes": "",
            }
        ]
    }
    article_text = _normalize_space(f"{article.title}\n{article.content_text}")[:MAX_LLM_TEXT_CHARS]
    return (
        "Return JSON matching this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        "Candidate recall, only keep concrete resources:\n"
        f"{json.dumps(candidate_payload, ensure_ascii=False)}\n\n"
        "Article:\n"
        f"{article_text}"
    )


def _resource_from_llm_item(item: dict[str, Any]) -> ExtractedResource | None:
    name = _clean_name(str(item.get("name", "")))
    evidence = _normalize_space(str(item.get("evidence_snippet", "")))
    if not name or not evidence:
        return None
    tags = [_clean_tag(str(tag)) for tag in item.get("capability_tags", []) if _clean_tag(str(tag))]
    links = [str(link).strip() for link in item.get("links", []) if str(link).startswith(("http://", "https://"))]
    confidence = _clamp_float(item.get("confidence", 0.78), 0.0, 1.0)
    return ExtractedResource(
        name=normalize_name(name),
        aliases=[_clean_name(str(alias)) for alias in item.get("aliases", []) if _clean_name(str(alias))],
        resource_type=str(item.get("type") or "tool"),
        summary=_normalize_space(str(item.get("summary") or evidence))[:180],
        capability_tags=_unique(tags),
        links=_unique(links),
        evidence_snippet=evidence[:280],
        confidence=confidence,
        risk_level=str(item.get("risk_level") or "low"),
        risk_notes=str(item.get("risk_notes") or ""),
    )


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[\u3002\uff01\uff1f!?;\uff1b\n\r]+", text) if s.strip()]


def _resource_like(text: str) -> bool:
    lowered = text.lower()
    return any(hint.lower() in lowered for hint in RESOURCE_HINTS) or bool(_links(text))


def _candidate_names(sentence: str) -> list[str]:
    text = re.sub(r"https?://[^\s\uff0c\u3002\uff1b;]+", "", sentence).strip()
    names: list[str] = []

    intro_patterns = [
        r"([A-Za-z][A-Za-z0-9]*(?:[ ._-][A-Za-z0-9]+){0,3})\s*(?:\u662f\u4e00[\u6b3e\u4e2a]|\u53ef\u4ee5|\u9002\u5408|\u652f\u6301)",
        r"([\u4e00-\u9fa5A-Za-z0-9 _.-]{2,24}?)\s*(?:\u662f\u4e00[\u6b3e\u4e2a]|\u53ef\u4ee5|\u9002\u5408|\u652f\u6301)",
        r"([\u4e00-\u9fa5A-Za-z0-9 _.-]{2,24}?)\s*(?:鏄竴娆|鏄竴涓|鏀寔)",
        r"(?:\u63a8\u8350|\u5206\u4eab|\u5b89\u5229|\u4ecb\u7ecd)\s*([A-Za-z][A-Za-z0-9]*(?:[ ._-][A-Za-z0-9]+){0,3})",
    ]
    for pattern in intro_patterns:
        for match in re.finditer(pattern, text):
            names.append(match.group(1))

    for match in re.finditer(r"\b([A-Z][A-Za-z0-9]*(?:[ ._-](?:AI|PDF|TV|Reader|App|[A-Z][A-Za-z0-9]*)){0,3})\b", text):
        names.append(match.group(1))

    cleaned: list[str] = []
    for name in names:
        clean = _clean_name(name)
        if clean and clean not in cleaned:
            cleaned.append(clean)
    return cleaned[:8]


def _clean_name(name: str) -> str:
    value = _normalize_space(name).strip(" \t,.\uff0c\u3002\uff1b:：()[]\uff08\uff09")
    value = re.split(r"[\uff0c\u3002\uff1b;]", value)[0].strip()
    value = re.split(r"(?:\u662f\u4e00[\u6b3e\u4e2a]|\u66fe\u7ecf|\u53ef\u4ee5|\u9002\u5408|\u652f\u6301)", value)[0].strip()
    value = re.split(r"(?:鏄竴娆|鏄竴涓|鏀寔)", value)[0].strip()
    value = re.sub(r"^(?:\u8fd9\u4e2a|\u8fd9\u6b3e|\u4e00\u6b3e|\u4e00\u4e2a|\u5f00\u6e90|\u672c\u5730\u5316|\u514d\u8d39)+", "", value).strip()
    value = re.sub(r"(?:\u6700\u65b0\u7248|\u65b0\u7248|\u66f4\u65b0|\u4e0b\u8f7d|\u5b98\u7f51|\u9879\u76ee\u5730\u5740)$", "", value).strip()
    compact = re.sub(r"\s+", "", value)
    if not value or len(value) < 2 or len(value) > 40:
        return ""
    if value in GENERIC_NAMES or compact in GENERIC_NAMES:
        return ""
    if any(word in value for word in TITLE_NOISE) and not re.search(r"[A-Za-z0-9]", value):
        return ""
    if any(part in value for part in INVALID_NAME_PARTS):
        return ""
    if len(value) > 18 and not re.search(r"[A-Za-z0-9]", value):
        return ""
    return value


def _valid_resource_name(name: str, article: StandardArticle | None = None, evidence: str = "") -> bool:
    clean = _clean_name(name)
    if not clean or clean in GENERIC_NAMES:
        return False
    if article and clean == article.source_name.strip():
        return False
    if article and clean == article.title.strip():
        return False
    if article and clean in article.title and any(word in article.title for word in TITLE_NOISE) and len(clean) > 18:
        return False
    if evidence and clean in evidence:
        index = evidence.find(clean)
        nearby = evidence[max(0, index - 80) : index + len(clean) + 80]
        if "\u516c\u4f17\u53f7" in nearby and any(word in nearby for word in ["\u5173\u6ce8", "\u804a\u5929\u6846", "\u53d1\u9001\u6570\u5b57"]):
            return False
    if evidence and clean not in evidence and not any(alias in evidence for alias in clean.split()):
        return False
    return True


def _links(text: str) -> list[str]:
    return _unique(re.findall(r"https?://[^\s\uff0c\u3002\uff1b;\u3001]+", text))


def _infer_tags(text: str) -> list[str]:
    checks = [
        ("\u514d\u8d39\u542c\u6b4c", "\u542c\u6b4c" in text or "\u97f3\u4e50" in text),
        ("\u8ffd\u5267", "\u8ffd\u5267" in text or "\u5728\u7ebf\u89c2\u770b" in text),
        ("\u56fe\u7247\u9ad8\u6e05\u5316", "\u56fe\u7247" in text or "\u9ad8\u6e05\u5316" in text),
        ("\u6587\u6863\u5904\u7406", "PDF" in text or "\u6587\u6863" in text),
        ("\u9605\u8bfb\u5de5\u5177", "\u9605\u8bfb" in text or "\u7a0d\u540e\u8bfb" in text),
        ("AI \u6548\u7387", "AI" in text or "\u6548\u7387" in text),
        ("\u5f00\u6e90\u9879\u76ee", "\u5f00\u6e90" in text or "GitHub" in text or "github.com" in text.lower()),
        ("API \u8c03\u8bd5", "API" in text or "HTTP" in text),
        ("\u77e5\u8bc6\u7ba1\u7406", "\u77e5\u8bc6\u5e93" in text or "\u77e5\u8bc6\u7ba1\u7406" in text),
        ("鍏嶈垂鍚瓕", "鍏嶈垂" in text or "鍚瓕" in text or "闊充箰" in text),
        ("闊充箰涓嬭浇", "闊充箰" in text or "涓嬭浇" in text),
    ]
    return _unique([tag for tag, matched in checks if matched])


def _guess_type(text: str) -> str:
    if any(word in text for word in ["App", "APP", "Android", "iOS", "\u5e94\u7528"]):
        return "app"
    if "\u7f51\u7ad9" in text or "Web" in text:
        return "website"
    if "\u63d2\u4ef6" in text:
        return "plugin"
    if "\u9879\u76ee" in text or "\u5f00\u6e90" in text or "GitHub" in text:
        return "project"
    return "tool"


def _summary_for(evidence: str, name: str, tags: list[str]) -> str:
    cleaned = re.sub(r"https?://[^\s\uff0c\u3002\uff1b;\u3001]+", "", evidence).strip()
    if tags:
        return f"{name}: {cleaned[:90]} ({', '.join(tags[:4])})"
    return cleaned[:120] or f"{name} resource"


def _has_risk_signal(text: str) -> bool:
    return any(
        word in text
        for word in [
            "\u505c\u6b62\u7ef4\u62a4",
            "\u4e0d\u7a33\u5b9a",
            "\u5931\u6548",
            "\u4e0b\u67b6",
            "\u98ce\u9669",
            "\u7070\u8272",
            "\u76d7\u7248",
            "\u955c\u50cf",
        ]
    )


def _dedupe_resources(resources: list[ExtractedResource], article: StandardArticle | None = None) -> list[ExtractedResource]:
    deduped: dict[str, ExtractedResource] = {}
    for item in resources:
        clean = _clean_name(item.name)
        if not clean or not _valid_resource_name(clean, article, item.evidence_snippet):
            continue
        item.name = normalize_name(clean)
        key = re.sub(r"[\s._-]+", "", item.name).lower()
        existing = deduped.get(key)
        if existing is None or item.confidence > existing.confidence:
            deduped[key] = item
        elif existing:
            existing.links = _unique([*existing.links, *item.links])
            existing.capability_tags = _unique([*existing.capability_tags, *item.capability_tags])
    return sorted(deduped.values(), key=lambda item: item.confidence, reverse=True)[:12]


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _clean_tag(tag: str) -> str:
    value = _normalize_space(tag).strip(" ,.\uff0c\u3002\uff1b:")
    if not value or len(value) > 24:
        return ""
    return value


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _clamp_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return minimum
    return max(min(numeric, maximum), minimum)
