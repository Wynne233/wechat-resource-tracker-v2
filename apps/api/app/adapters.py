from __future__ import annotations

import csv
import json
import re
import sqlite3
import tempfile
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

from .schemas import StandardArticle


def parse_wechat_exporter_content(content: str, fallback_source_name: str = "") -> list[StandardArticle]:
    """Best-effort parser for wechat-article-exporter JSON/HTML/Markdown/Text exports."""
    text = content.strip()
    if not text:
        return []
    if text[0] in "[{":
        return [_article_from_mapping(item, fallback_source_name, "history_export") for item in _json_items(text)]
    if _looks_like_csv(text):
        return [_article_from_mapping(item, fallback_source_name, "history_export") for item in _csv_items(text)]
    return [_article_from_text_blob(text, fallback_source_name, "history_export")]


def parse_supplement_content(
    content: str,
    source_name: str,
    article_url: str,
    title: str = "",
    published_at: datetime | None = None,
) -> list[StandardArticle]:
    text = content.strip()
    if not text:
        return []
    return [
        StandardArticle(
            source_name=source_name or "补充导入",
            source_identifier=None,
            title=title or _title_from_html(text) or _first_text_line(text) or "补充导入文章",
            article_url=article_url,
            published_at=published_at,
            content_text=_html_to_text(text),
            content_html=text if "<" in text and ">" in text else "",
            crawl_source="url_import",
            raw_payload={"adapter": "supplement_import"},
        )
    ]


def fetch_wewe_rss_articles(feed_url: str, auth_code: str | None = None, timeout: float = 60.0) -> list[StandardArticle]:
    headers = {"User-Agent": "wechat-resource-tracker-v2/0.1"}
    if auth_code:
        headers["Authorization"] = auth_code
    response = httpx.get(feed_url, headers=headers, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    body = response.text.strip()
    content_type = response.headers.get("content-type", "")
    if "json" in content_type or body.startswith("{") or body.startswith("["):
        return [_article_from_mapping(item, "", "rss_sync") for item in _json_items(body)]
    return _articles_from_feed_xml(body)


def fetch_wewe_rss_local_articles(limit: int = 1000) -> list[StandardArticle]:
    db_file = Path(tempfile.gettempdir()) / "wechat-resource-tracker-v2" / "wewe-rss.db"
    if not db_file.exists():
        raise RuntimeError(f"未找到 wewe-rss 本地数据库：{db_file}")

    connection = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                articles.id,
                articles.mp_id,
                articles.title,
                articles.pic_url,
                articles.publish_time,
                feeds.mp_name,
                feeds.mp_intro
            FROM articles
            LEFT JOIN feeds ON feeds.id = articles.mp_id
            ORDER BY articles.publish_time DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        connection.close()

    articles: list[StandardArticle] = []
    for row in rows:
        article_id = str(row["id"])
        source_name = row["mp_name"] or f"未知公众号-{row['mp_id']}"
        title = row["title"] or "未命名文章"
        articles.append(
            StandardArticle(
                source_name=source_name,
                source_identifier=row["mp_id"],
                title=title,
                article_url=f"https://mp.weixin.qq.com/s/{article_id}",
                published_at=datetime.fromtimestamp(row["publish_time"]) if row["publish_time"] else None,
                content_text="",
                content_html="",
                crawl_source="wewe_rss_sqlite",
                raw_payload={
                    "adapter": "wewe_rss_sqlite",
                    "id": article_id,
                    "mp_id": row["mp_id"],
                    "title": title,
                    "pic_url": row["pic_url"],
                    "publish_time": row["publish_time"],
                    "mp_name": source_name,
                    "mp_intro": row["mp_intro"],
                    "content_status": "missing",
                },
            )
        )
    return articles


def _json_items(text: str) -> list[dict[str, Any]]:
    payload = json.loads(text)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ["articles", "items", "data", "list", "results", "entries"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _items_from_nested_dict(value)
            if nested:
                return nested
    return [payload]


def _items_from_nested_dict(value: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["articles", "items", "list", "results", "entries"]:
        nested = value.get(key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    return []


def _csv_items(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(StringIO(text))
    return [dict(row) for row in reader]


def _looks_like_csv(text: str) -> bool:
    first = text.splitlines()[0].lower()
    return "," in first and any(key in first for key in ["title", "标题", "article", "url", "链接"])


def _article_from_mapping(item: dict[str, Any], fallback_source_name: str, crawl_source: str) -> StandardArticle:
    title = _pick(item, "title", "标题", "article_title", "articleTitle", "name") or "未命名文章"
    source_name = (
        _pick(
            item,
            "source_name",
            "sourceName",
            "account_name",
            "accountName",
            "_accountName",
            "mp_name",
            "mpName",
            "nickname",
            "nickName",
            "公众号",
            "author",
            "作者",
        )
        or fallback_source_name
        or "未知公众号"
    )
    url = _pick(item, "article_url", "articleUrl", "url", "link", "content_url", "contentUrl", "原文链接", "链接")
    content_html = _pick(item, "content_html", "contentHtml", "html", "正文HTML", "正文 HTML") or ""
    content_text = _pick(item, "content_text", "contentText", "content", "正文", "text", "markdown", "md") or _html_to_text(content_html)
    if not url:
        url = _synthetic_url(source_name, title)
    return StandardArticle(
        source_name=source_name,
        source_identifier=_pick(item, "source_identifier", "sourceIdentifier", "account_id", "accountId", "_biz", "biz", "mp_id", "mpId", "公众号标识"),
        title=title,
        article_url=url,
        published_at=_parse_datetime(_pick(item, "published_at", "publishedAt", "publish_time", "publishTime", "pubDate", "发布时间", "date")),
        content_text=_html_to_text(content_text),
        content_html=content_html,
        read_count=_parse_int(_pick(item, "read_count", "readCount", "阅读量")),
        like_count=_parse_int(_pick(item, "like_count", "likeCount", "点赞", "点赞数")),
        comment_count=_parse_int(_pick(item, "comment_count", "commentCount", "评论", "评论数")),
        crawl_source=crawl_source,
        raw_payload=item,
    )


def _article_from_text_blob(text: str, fallback_source_name: str, crawl_source: str) -> StandardArticle:
    return StandardArticle(
        source_name=fallback_source_name or "历史导入",
        title=_title_from_html(text) or _first_text_line(text) or "历史导入文章",
        article_url=_first_url(text) or _synthetic_url(fallback_source_name or "history", _first_text_line(text) or "article"),
        published_at=None,
        content_text=_html_to_text(text),
        content_html=text if "<" in text and ">" in text else "",
        crawl_source=crawl_source,
        raw_payload={"adapter": "wechat_article_exporter_text"},
    )


def _articles_from_feed_xml(text: str) -> list[StandardArticle]:
    root = ElementTree.fromstring(text)
    items = root.findall(".//item")
    if not items:
        items = root.findall("{http://www.w3.org/2005/Atom}entry")
    articles: list[StandardArticle] = []
    for item in items:
        title = _xml_text(item, "title") or "未命名文章"
        link = _xml_text(item, "link")
        if not link:
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.attrib.get("href", "") if atom_link is not None else ""
        content_html = _xml_text(item, "encoded") or _xml_text(item, "description") or _xml_text(item, "content") or ""
        source_name = _xml_text(item, "author") or _xml_text(item, "creator") or "未知公众号"
        articles.append(
            StandardArticle(
                source_name=source_name,
                title=title,
                article_url=link or _synthetic_url(source_name, title),
                published_at=_parse_datetime(_xml_text(item, "pubDate") or _xml_text(item, "published") or _xml_text(item, "updated")),
                content_text=_html_to_text(content_html),
                content_html=content_html,
                crawl_source="rss_sync",
                raw_payload={"adapter": "wewe_rss_xml"},
            )
        )
    return articles


def _xml_text(item: ElementTree.Element, tag_name: str) -> str:
    for child in item.iter():
        if child.tag.split("}")[-1] == tag_name and child.text:
            return child.text.strip()
    return ""


def _pick(item: dict[str, Any], *keys: str) -> str:
    lowered = {key.lower(): value for key, value in item.items()}
    for key in keys:
        value = item.get(key)
        if value is None:
            value = lowered.get(key.lower())
        if value is None:
            continue
        value_text = str(value).strip()
        if value_text:
            return value_text
    return ""


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).replace(tzinfo=None)
    except (TypeError, ValueError, IndexError):
        return None


def _parse_int(value: str) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def _html_to_text(text: str) -> str:
    text = re.sub(r"<(script|style).*?</\1>", "", text, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _title_from_html(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    if match:
        return _html_to_text(match.group(1))
    match = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.I | re.S)
    return _html_to_text(match.group(1)) if match else ""


def _first_text_line(text: str) -> str:
    plain = _html_to_text(text)
    return next((line.strip() for line in plain.splitlines() if line.strip()), plain[:80]).strip()


def _first_url(text: str) -> str:
    match = re.search(r"https?://[^\s\"'<>]+", text)
    return match.group(0) if match else ""


def _synthetic_url(source_name: str, title: str) -> str:
    safe_source = re.sub(r"[^a-zA-Z0-9]+", "-", source_name).strip("-").lower() or "source"
    safe_title = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower() or "article"
    return f"urn:article:{safe_source}:{safe_title}"


def host_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.path
