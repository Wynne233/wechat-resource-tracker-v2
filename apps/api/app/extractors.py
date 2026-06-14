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


EXTRACTION_VERSION = "mvp-hybrid-v1"
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
    "工具",
    "软件",
    "App",
    "APP",
    "应用",
    "插件",
    "网站",
    "平台",
    "网盘",
    "听歌",
    "追剧",
    "AI",
    "剪辑",
    "图片",
    "效率",
    "下载",
    "播放器",
    "助手",
    "神器",
    "更新",
    "限免",
    "开源",
    "书源",
    "音源",
    "音乐",
    "阅读",
    "高清化",
    "B站",
    "Bilibili",
]

PLATFORM_HINTS = ["Windows", "macOS", "iOS", "Android", "Web", "Linux"]
GENERIC_NAMES = {
    "AI",
    "App",
    "APP",
    "Web",
    "Windows",
    "Android",
    "macOS",
    "iOS",
    "PC",
    "B站",
    "Bilibili",
    "音乐",
    "听歌",
    "免费听歌",
    "更新",
    "下载",
    "神器",
    "软件",
    "工具",
    "助手",
    "应用",
    "资源",
    "网站",
    "平台",
    "官网",
    "官方网站",
    "下载地址",
    "链接",
    "原文链接",
}

INVALID_NAME_PARTS = [
    "大家好",
    "今天给大家",
    "一款好用",
    "两款",
    "几款",
    "仅支持",
    "不过软件",
    "开屏广告",
    "点击蓝字",
    "关注我们",
    "扫描二维码",
    "每日壁纸",
    "提供的所有下载文件",
    "下载后的24小时",
    "倒下了",
    "站起来",
]

INVALID_NAME_PREFIXES = ("Part.", "Tech.Part", "注释", "声明")


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
    title = article.title.strip()
    body = article.content_text.strip()
    text = "\n".join(part for part in [title, body] if part)
    if not text:
        return []

    sentences = _sentences(text)
    resources: list[ExtractedResource] = []

    title_names = _candidate_names(title)
    for name in title_names:
        evidence = title[:280]
        resources.append(_make_resource(name, evidence, text, article, content_status, from_title=True))

    for sentence in sentences:
        if not _resource_like(sentence):
            continue
        names = _candidate_names(sentence)
        for name in names:
            resources.append(_make_resource(name, sentence[:280], text, article, content_status, from_title=False))

    return resources


def _make_resource(
    name: str,
    evidence: str,
    whole_text: str,
    article: StandardArticle,
    content_status: str,
    from_title: bool,
) -> ExtractedResource:
    links = _links(evidence) or _links(whole_text)
    platforms = [p for p in PLATFORM_HINTS if p.lower() in whole_text.lower()]
    tags = _infer_tags(f"{article.title}\n{evidence}\n{whole_text}")
    confidence = 0.84 if links and content_status == "full_text" else 0.74 if content_status in {"full_text", "partial_text"} else 0.52
    if from_title and content_status == "title_only":
        confidence = min(confidence, 0.56)
    risk_level = "medium" if any(word in whole_text for word in ["破解", "灰色", "不稳定", "风险", "镜像", "盗版"]) else "low"
    return ExtractedResource(
        name=normalize_name(name),
        resource_type=_guess_type(whole_text),
        summary=_summary_for(evidence, name, tags, content_status),
        capability_tags=tags,
        platforms=platforms,
        links=links,
        evidence_snippet=evidence,
        confidence=confidence,
        risk_level=risk_level,
        risk_notes="存在风险线索，建议人工复核。" if risk_level != "low" else "",
    )


def _llm_extract(article: StandardArticle, candidates: list[ExtractedResource]) -> list[ExtractedResource]:
    api_key = os.getenv("RESOURCE_EXTRACTOR_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    enabled = os.getenv("RESOURCE_EXTRACTOR_LLM_ENABLED", "auto").lower()
    if enabled in {"0", "false", "off", "no"} or not api_key:
        return []

    endpoint = _chat_completions_endpoint()
    model = os.getenv("RESOURCE_EXTRACTOR_MODEL") or ("deepseek-v4-flash" if os.getenv("DEEPSEEK_API_KEY") else "gpt-4o-mini")
    prompt = _llm_prompt(article, candidates)
    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是严谨的中文公众号资源情报分析员，任务是从文章全文中抽取真实可追踪的资源实体。"
                    "资源实体只能是具体软件、App、网站、插件、开源项目、资料包、课程、模型、数据集或服务名称。"
                    "禁止把功能词、类别词、营销词、标题短语、形容词或泛称当资源名。"
                    "必须严格输出 JSON 对象，不要输出 Markdown、解释文字或代码块。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    if model.startswith("deepseek-v4"):
        payload["thinking"] = {"type": "disabled"}
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []

    content = raw.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
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
        {
            "name": item.name,
            "evidence": item.evidence_snippet,
            "tags": item.capability_tags,
            "links": item.links,
        }
        for item in candidates[:12]
    ]
    article_text = _normalize_space(f"{article.title}\n{article.content_text}")[:MAX_LLM_TEXT_CHARS]
    schema = {
        "resources": [
            {
                "name": "具体资源名",
                "aliases": ["别名"],
                "type": "app|website|tool|plugin|dataset|project|other",
                "capability_tags": ["免费听歌", "B站音乐"],
                "summary": "一句话说明资源解决什么问题",
                "links": ["https://..."],
                "evidence_snippet": "文章中的原文证据",
                "confidence": 0.0,
                "risk_level": "low|medium|high",
                "risk_notes": "",
            }
        ]
    }
    return (
        "请从这篇公众号文章全文中识别真实资源实体，并按要求输出 JSON。\n\n"
        "核心目标：\n"
        "- 找出文章真正推荐、介绍、测评、分享或提供下载的资源。\n"
        "- 资源名必须能作为用户搜索和后续追踪的实体名称。\n"
        "- 用户也会用功能词搜索，所以必须把能力、用途、场景写入 capability_tags。\n\n"
        "资源名判定规则：\n"
        "1. 资源名必须是具体名称，如 BBPlayer、敦伦调调、MusicFree、洛雪音乐助手、Upscayl。\n"
        "2. 不能把泛词当资源名，例如：听歌、免费听歌、APP、软件、工具、神器、网站、项目、下载地址、官网、必装、复活、低调使用。\n"
        "3. 不能把完整标题或标题宣传语当资源名，例如“电脑也能用酷狗概念版免费听歌”不是资源名，应识别为“酷狗概念版”。\n"
        "4. 如果无法从正文证据中确认具体资源名，不要输出该资源。\n"
        "5. 同一资源在文章中多次出现时只输出一次，别名放入 aliases。\n\n"
        "证据和链接规则：\n"
        "6. 每个资源必须有 evidence_snippet，必须来自文章原文，能证明该资源的名称和用途。\n"
        "7. 如果文章提供官网、GitHub、下载页、网盘、App Store、项目地址等链接，请放入 links。\n"
        "8. 如果链接只是公众号原文链接、广告链接或无关跳转，不要作为资源链接。\n\n"
        "能力标签规则：\n"
        "9. capability_tags 写用户可能搜索的能力词、场景词和平台词，例如：免费听歌、B站音乐、音乐播放器、歌词、无损音乐、Windows、Android。\n"
        "10. capability_tags 不要重复资源名，也不要只写空泛词。\n\n"
        "风险规则：\n"
        "11. 如果文章出现破解、盗版、灰色、失效、不稳定、镜像、非官方、广告多等风险线索，risk_level 至少为 medium，并在 risk_notes 说明。\n"
        "12. 如果文章没有真实资源，resources 必须返回空数组。\n\n"
        f"候选召回：{json.dumps(candidate_payload, ensure_ascii=False)}\n\n"
        f"必须遵守的 JSON schema 示例：{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"文章：{article_text}"
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


def _valid_resource_name(name: str, article: StandardArticle | None = None, evidence: str = "") -> bool:
    clean = _clean_name(name)
    if not clean:
        return False
    if clean in GENERIC_NAMES:
        return False
    if any(clean.startswith(prefix) for prefix in INVALID_NAME_PREFIXES):
        return False
    if any(part in clean for part in INVALID_NAME_PARTS):
        return False
    if re.match(r"^[一二三四五六七八九十两几多]\s*[款个套]", clean):
        return False
    if article and article.source_name and clean == article.source_name.strip():
        return False
    if evidence and clean in evidence and "公众号" in evidence and any(word in evidence for word in ["关注", "聊天框", "回复", "暗号", "发送"]):
        return False
    if len(clean) > 18 and not re.search(r"[A-Za-z0-9]", clean):
        return False
    if len(clean) > 12 and any(word in clean for word in ["软件", "平台", "广告", "下载", "资源", "大家"]):
        return False
    return True


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？!?\n\r]+", text) if s.strip()]


def _resource_like(text: str) -> bool:
    lowered = text.lower()
    return any(hint.lower() in lowered for hint in RESOURCE_HINTS) or bool(_links(text))


def _candidate_names(sentence: str) -> list[str]:
    names: list[str] = []
    title = re.sub(r"https?://[^\s，。；、)）]+", "", sentence).strip()

    for match in re.finditer(r"[【\[]([^【】\[\]]{2,40})[】\]]", title):
        names.append(match.group(1).strip())

    if "-" in title or "：" in title or ":" in title:
        parts = [part.strip() for part in re.split(r"[-：:]", title) if part.strip()]
        for part in parts[1:]:
            names.extend(_split_name_list(part))

    patterns = [
        r"用\s*([\u4e00-\u9fa5A-Za-z0-9 _-]{2,18})(?:免费听歌|听歌|免费看|免费听)",
        r"([\u4e00-\u9fa5A-Za-z0-9 _-]{2,18})(?:概念版|专业版|增强版|纯净版)?(?:免费听歌|听歌|音乐播放|播放器)",
        r"(?:叫做|叫|名为|推荐|安利|介绍)\s*([A-Za-z][A-Za-z0-9 ._-]{1,32})",
        r"(?:叫做|叫|名为|推荐|安利|介绍)\s*([\u4e00-\u9fa5A-Za-z0-9 _-]{2,20})",
        r"([\u4e00-\u9fa5A-Za-z0-9 _-]{2,20})这个(?:免费)?(?:APP|App|应用|软件|工具|网站)",
        r"([\u4e00-\u9fa5A-Za-z0-9 _-]{2,20})(?:是一款|是一个|是一套|为一款|作为一款)(?:免费|开源|本地)?(?:APP|App|应用|软件|工具|网站|播放器|助手|插件)",
        r"^([\u4e00-\u9fa5A-Za-z0-9 _-]{2,20})(?:最新版本|最新版|更新|下载|支持|，|,|（|\(|$)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, title):
            raw = re.split(r"[，。；、!！?？]", match.group(1))[0]
            names.append(raw.strip())

    for match in re.finditer(r"\b([A-Z][A-Za-z0-9]+(?:[ ._-][A-Z]?[A-Za-z0-9]+){0,3})\b", title):
        raw = match.group(1).strip(" ，。；:：()（）")
        names.append(raw)

    return [_clean_name(name) for name in names if _clean_name(name)][:8]


def _split_name_list(text: str) -> list[str]:
    value = re.split(r"[，。！？；\n]", text)[0]
    return [part.strip() for part in re.split(r"[、，和与]+", value) if part.strip()]


def _clean_name(name: str) -> str:
    value = _normalize_space(name).strip(" \t，。；:：-[]【】()（）")
    if "-" in value and any(word in value.split("-", 1)[0] for word in ["神器", "工具", "软件", "播放", "下载", "超好用"]):
        value = value.rsplit("-", 1)[-1].strip()
    value = re.split(r"(?:是一款|是一个|是一套|为一款|作为一款)", value)[0].strip()
    value = re.sub(r"^(?:电脑也能用|手机也能用|安卓也能用|Windows也能用|又一款|一款|这个|这款|用)", "", value).strip()
    value = re.split(r"\s+(?:免费|最新|更新|APP|App|应用|软件|工具|网站|下载|听歌|音乐)", value)[0].strip()
    value = re.sub(r"(?:新版|最新版本|最新版)?(?:免费听歌|听歌神器|听歌|音乐播放(?:器)?|播放器|下载神器|神器)$", "", value).strip()
    value = re.sub(r"新版音乐$", "", value).strip()
    value = re.sub(r"^(一款|一个|这款|这个|最新|超好用|好用|免费|开源|本地|无损|音乐|下载|神器|更新)+", "", value)
    value = re.sub(
        r"(最新版本|最新版|更新|下载|分享|支持在线播放|附最新.*|附可用.*|免费版|破解版|免费|这个|这款|APP|App|应用)$",
        "",
        value,
    ).strip()
    compact = re.sub(r"\s+", "", value)
    if value in GENERIC_NAMES or compact in GENERIC_NAMES or len(value) < 2:
        return ""
    if any(word in value for word in ["合集", "推荐", "清单", "大全", "汇总", "盘点"]) and not re.search(r"[A-Za-z0-9]", value):
        return ""
    if compact in {"AI工具合集", "工具合集", "软件合集", "资源合集"}:
        return ""
    if re.fullmatch(r"(?:又)?一?款?(?:免费)?(?:的)?(?:B站)?(?:音乐)?(?:听歌)?(?:播放)?(?:器|软件|工具|神器|APP|App)?", value):
        return ""
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", value) and value in GENERIC_NAMES:
        return ""
    if len(value) > 40:
        return ""
    return value


def _clean_tag(tag: str) -> str:
    value = _normalize_space(tag).strip(" ，。；:：")
    if not value or len(value) > 18:
        return ""
    return value


def _links(text: str) -> list[str]:
    return _unique(re.findall(r"https?://[^\s，。；、)）]+", text))


def _infer_tags(text: str) -> list[str]:
    tags: list[str] = []
    lowered = text.lower()
    checks = [
        ("免费听歌", "免费" in text and "听歌" in text),
        ("B站音乐", "B站" in text or "bilibili" in lowered),
        ("音乐播放器", "音乐" in text or "听歌" in text or "播放器" in text),
        ("无损音乐", "无损" in text),
        ("在线播放", "在线播放" in text or "在线播放" in text),
        ("图片高清化", "高清化" in text or "图片" in text),
        ("阅读工具", "阅读" in text),
        ("AI工具", "AI" in text or "人工智能" in text),
        ("剪辑工具", "剪辑" in text),
        ("开源项目", "开源" in text),
        ("效率工具", "效率" in text),
        ("资料下载", "下载" in text),
    ]
    for tag, matched in checks:
        if matched:
            tags.append(tag)
    return _unique(tags)


def _guess_type(text: str) -> str:
    if any(word in text for word in ["App", "APP", "应用", "Android", "iOS"]):
        return "app"
    if "网站" in text or "Web" in text:
        return "website"
    if "插件" in text:
        return "plugin"
    if "资料" in text or "合集" in text:
        return "dataset"
    return "tool"


def _summary_for(evidence: str, name: str, tags: list[str], content_status: str) -> str:
    cleaned = re.sub(r"https?://[^\s，。；、)）]+", "", evidence).strip()
    if content_status == "title_only":
        prefix = "仅从标题弱识别，需补全文复核"
        return f"{prefix}：{cleaned[:70] or name}"
    if tags:
        return f"{name}：{cleaned[:90]}（能力：{'、'.join(tags[:4])}）"
    return cleaned[:120] or f"{name} 资源"


def _dedupe_resources(resources: list[ExtractedResource], article: StandardArticle | None = None) -> list[ExtractedResource]:
    deduped: dict[str, ExtractedResource] = {}
    for item in resources:
        clean = _clean_name(item.name)
        if not clean or not _valid_resource_name(clean, article, item.evidence_snippet):
            continue
        item.name = normalize_name(clean)
        key = item.name.lower()
        existing = deduped.get(key)
        if existing is None or item.confidence > existing.confidence:
            item.capability_tags = _unique(item.capability_tags)
            item.links = _unique(item.links)
            item.aliases = _unique([alias for alias in item.aliases if _clean_name(alias)])
            deduped[key] = item
        else:
            existing.capability_tags = _unique([*existing.capability_tags, *item.capability_tags])
            existing.links = _unique([*existing.links, *item.links])
            existing.aliases = _unique([*existing.aliases, *item.aliases])
    return sorted(deduped.values(), key=lambda item: item.confidence, reverse=True)


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


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
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))
