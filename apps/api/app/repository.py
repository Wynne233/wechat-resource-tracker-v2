from __future__ import annotations

from datetime import datetime, timedelta
from html.parser import HTMLParser
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .adapters import (
    fetch_wewe_rss_articles,
    fetch_wewe_rss_local_articles,
    parse_supplement_content,
    parse_wechat_exporter_content,
)
from .db import DATABASE_URL, DB_FILE
from .extractors import EXTRACTION_VERSION, ExtractedResource, detect_content_status, extract_resources
from .models import (
    Article,
    IntegrationConfig,
    ManualReview,
    Notification,
    NotificationSetting,
    Resource,
    ResourceMention,
    ResourceScore,
    SourceAccount,
    StatusCheck,
    Subscription,
    TaskLog,
)
from .schemas import (
    AdminOverview,
    AdminResourceListResponse,
    AnalyzedResource,
    AdapterImportRequest,
    ArticleAnalyzeRequest,
    ArticleAnalyzeResponse,
    FeishuSettingRead,
    HistoryImportRequest,
    HistoryImportResponse,
    IntegrationConfigRead,
    ImportResultItem,
    ManualReviewRequest,
    ManualReviewResponse,
    NotificationRead,
    ResourceDetail,
    ResourceBulkActionResponse,
    ResourceBulkUpdateRequest,
    ScoreBreakdown,
    SearchResource,
    SearchResponse,
    SourceCreate,
    SourceCheckResponse,
    SourceEvidence,
    SourceRead,
    SourceTrackingRequest,
    StandardArticle,
    StatusTimelineItem,
    SupplementImportRequest,
    SubscriptionCreate,
    SubscriptionRead,
    TaskLogRead,
    WeweRssConfigRequest,
    WeweRssSyncRequest,
)
from .scoring import recalculate_resource_score
from .utils import canonical_key, mask_webhook, new_id, now, trust_weight


SOURCE_CHECK_COOLDOWN = timedelta(minutes=30)
SOURCE_CHECK_INTERVAL = timedelta(days=7)


def configured_exporter_base_url(requested_url: str = "") -> str:
    return (
        requested_url.strip()
        or os.getenv("WECHAT_EXPORTER_BASE_URL", "").strip()
        or "http://127.0.0.1:4100"
    )


def configured_wewe_rss_feed_url(requested_url: str = "") -> str:
    return requested_url.strip() or os.getenv("WEWE_RSS_FEED_URL", "").strip()


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def ensure_source(session: Session, payload: SourceCreate | StandardArticle) -> SourceAccount:
    name = payload.name if isinstance(payload, SourceCreate) else payload.source_name
    source = session.scalar(select(SourceAccount).where(SourceAccount.name == name))
    if source:
        return source

    level = payload.trust_level if isinstance(payload, SourceCreate) else "pending"
    source = SourceAccount(
        id=new_id("src"),
        name=name,
        source_identifier=getattr(payload, "source_identifier", None),
        source_type=getattr(payload, "source_type", "wechat"),
        trust_level=level,
        trust_weight=trust_weight(level),
        notes=getattr(payload, "notes", ""),
    )
    session.add(source)
    session.flush()
    return source


def activate_source_tracking(source: SourceAccount, tracking_source: str = "article_url_analysis") -> None:
    timestamp = now()
    source.tracking_status = "active"
    source.tracking_source = tracking_source
    source.first_tracked_at = source.first_tracked_at or timestamp
    source.last_analyzed_at = timestamp
    source.next_check_at = source.next_check_at or (timestamp + SOURCE_CHECK_INTERVAL)
    source.last_check_status = source.last_check_status or "pending"
    source.last_check_message = source.last_check_message or "已自动追踪，每周低频检查新文章。"


def create_source(session: Session, payload: SourceCreate) -> SourceRead:
    source = ensure_source(session, payload)
    source.source_identifier = payload.source_identifier
    source.source_type = payload.source_type
    source.trust_level = payload.trust_level
    source.trust_weight = trust_weight(payload.trust_level)
    source.notes = payload.notes
    session.commit()
    return source_to_read(session, source)


def list_sources(session: Session) -> list[SourceRead]:
    return [source_to_read(session, source) for source in session.scalars(select(SourceAccount).order_by(SourceAccount.name))]


def source_to_read(session: Session, source: SourceAccount) -> SourceRead:
    article_count = session.scalar(select(func.count(Article.id)).where(Article.source_id == source.id)) or 0
    resource_count = (
        session.scalar(
            select(func.count(func.distinct(ResourceMention.resource_id)))
            .join(Article, Article.id == ResourceMention.article_id)
            .where(Article.source_id == source.id)
        )
        or 0
    )
    return SourceRead(
        id=source.id,
        name=source.name,
        source_identifier=source.source_identifier,
        source_type=source.source_type,
        trust_level=source.trust_level,
        trust_weight=source.trust_weight,
        crawl_status=source.crawl_status,
        tracking_status=source.tracking_status,
        tracking_source=source.tracking_source,
        first_tracked_at=source.first_tracked_at,
        last_analyzed_at=source.last_analyzed_at,
        last_checked_at=source.last_checked_at,
        next_check_at=source.next_check_at,
        last_check_status=source.last_check_status,
        last_check_message=source.last_check_message,
        consecutive_failures=source.consecutive_failures,
        notes=source.notes,
        article_count=article_count,
        resource_count=resource_count,
    )


def import_history_json(session: Session, payload: HistoryImportRequest) -> HistoryImportResponse:
    return ingest_standard_articles(session, payload.articles, "history_json_import")


def import_wechat_exporter(session: Session, payload: AdapterImportRequest) -> HistoryImportResponse:
    articles = parse_wechat_exporter_content(payload.content, payload.source_name)
    return ingest_standard_articles(
        session,
        articles,
        "wechat_article_exporter_import",
        {"file_name": payload.file_name, "source_name": payload.source_name},
    )


def import_supplement(session: Session, payload: SupplementImportRequest) -> HistoryImportResponse:
    articles = parse_supplement_content(
        content=payload.content,
        source_name=payload.source_name,
        article_url=payload.article_url,
        title=payload.title,
        published_at=payload.published_at,
    )
    return ingest_standard_articles(session, articles, "supplement_import", {"article_url": payload.article_url})


class WechatArticleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.source_parts: list[str] = []
        self.content_parts: list[str] = []
        self._capture_title = False
        self._capture_source = False
        self._in_content = False
        self._content_depth = 0
        self.meta_title = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key: value or "" for key, value in attrs}
        node_id = attrs_map.get("id", "")
        if tag == "meta" and attrs_map.get("property") == "og:title":
            self.meta_title = attrs_map.get("content", "").strip()
        if tag == "h1" and node_id == "activity-name":
            self._capture_title = True
        if tag == "a" and node_id == "js_name":
            self._capture_source = True
        if node_id == "js_content":
            self._in_content = True
            self._content_depth = 1
            return
        if self._in_content:
            self._content_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._capture_title = False
        if tag == "a":
            self._capture_source = False
        if self._in_content:
            self._content_depth -= 1
            if self._content_depth <= 0:
                self._in_content = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._capture_title:
            self.title_parts.append(text)
        if self._capture_source:
            self.source_parts.append(text)
        if self._in_content:
            self.content_parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip() or self.meta_title

    @property
    def source_name(self) -> str:
        return " ".join(self.source_parts).strip()

    @property
    def content_text(self) -> str:
        return " ".join(self.content_parts).strip()


def analyze_article_url(session: Session, payload: ArticleAnalyzeRequest) -> ArticleAnalyzeResponse:
    article_url = payload.article_url.strip()
    exporter_base_url = configured_exporter_base_url(payload.exporter_base_url)
    if not is_valid_wechat_article_url(article_url):
        raise ValueError("请输入有效的微信公众号文章链接。")

    existing = session.scalar(select(Article).where(Article.article_url == article_url))
    before_resource_ids = {resource.id for resource in session.scalars(select(Resource)).all()}
    before_notification_count = session.scalar(select(func.count(Notification.id))) or 0

    try:
        article = fetch_article_from_exporter(article_url, exporter_base_url)
    except RuntimeError as exc:
        session.add(
            TaskLog(
                id=new_id("task"),
                task_type="article_url_analysis",
                status="failed",
                summary=f"文章链接分析失败：{exc}",
                payload={"article_url": article_url, "base_url": exporter_base_url},
            )
        )
        session.commit()
        raise ValueError(str(exc)) from exc

    result = ingest_standard_articles(
        session,
        [article],
        "article_url_analysis",
        {"article_url": article_url, "base_url": exporter_base_url},
    )

    source = ensure_source(session, article)
    activate_source_tracking(source, "article_url_analysis")
    create_source_subscription(session, source)

    stored = session.scalar(select(Article).where(Article.article_url == article_url))
    if stored:
        stored.source_id = source.id
    session.commit()

    touched_resources = resources_for_article(session, stored.id if stored else None)
    after_notification_count = session.scalar(select(func.count(Notification.id))) or 0
    created = sum(1 for resource in touched_resources if resource.id not in before_resource_ids)
    updated = max(len(touched_resources) - created, 0)
    status = stored.extraction_status if stored else ("skipped" if existing else "failed")
    content_status = stored.content_status if stored else detect_content_status(article)
    message = result.results[0].message if result.results else "文章分析完成。"
    if status == "no_resource":
        message = "文章已获取全文，但未发现明确可追踪资源。"

    return ArticleAnalyzeResponse(
        article_id=stored.id if stored else None,
        source_id=source.id,
        source_name=source.name,
        article_title=stored.title if stored else article.title,
        article_url=article_url,
        content_status=content_status,
        extraction_status=status,
        tracking_status=source.tracking_status,
        created_resources=created,
        updated_resources=updated,
        notifications_created=max(after_notification_count - before_notification_count, 0),
        resources=[resource_to_analyzed_item(resource, stored.id if stored else None) for resource in touched_resources],
        message=f"{message} 已自动追踪公众号：{source.name}。",
    )


def is_valid_wechat_article_url(article_url: str) -> bool:
    parts = urlsplit(article_url)
    return parts.scheme in {"http", "https"} and parts.netloc.endswith("mp.weixin.qq.com") and bool(parts.path.strip("/"))


def fetch_article_from_exporter(article_url: str, base_url: str = "http://127.0.0.1:4100") -> StandardArticle:
    text = fetch_text_from_exporter(article_url, base_url)
    metadata = fetch_json_from_exporter(article_url, base_url)
    title = pick_metadata(metadata, "title", "msg_title", "article_title", "articleTitle") or "公众号文章链接分析"
    source_name = (
        pick_metadata(metadata, "nickname", "nick_name", "source_name", "account_name", "author", "user_name")
        or pick_metadata(metadata, "biz", "__biz")
        or "公众号链接分析"
    )
    source_identifier = pick_metadata(metadata, "biz", "__biz", "source_identifier", "account_id")
    return StandardArticle(
        source_name=source_name,
        source_identifier=source_identifier,
        title=title,
        article_url=article_url,
        content_text=text,
        content_html="",
        crawl_source="article_url_analysis",
        raw_payload={"adapter": "wechat_article_exporter_download", "metadata": metadata},
    )


def fetch_json_from_exporter(article_url: str, base_url: str) -> dict:
    endpoint = f"{base_url.rstrip('/')}/api/public/v1/download?url={quote(article_url, safe='')}&format=json"
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return {}


def pick_metadata(payload: dict, *keys: str) -> str:
    if not payload:
        return ""
    lowered = {str(key).lower(): value for key, value in payload.items()}
    for key in keys:
        value = payload.get(key)
        if value is None:
            value = lowered.get(key.lower())
        if value:
            return str(value).strip()
    for value in payload.values():
        if isinstance(value, dict):
            nested = pick_metadata(value, *keys)
            if nested:
                return nested
    return ""


def fetch_article_directly_from_wechat(article_url: str) -> StandardArticle:
    request = urllib.request.Request(
        article_url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"直接访问微信文章失败：{exc}") from exc

    parser = WechatArticleHTMLParser()
    parser.feed(raw)
    title = parser.title or "公众号文章链接分析"
    source_name = parser.source_name or "公众号链接分析"
    content_text = parser.content_text
    if len(content_text) < 80:
        raise RuntimeError("微信页面未返回可解析正文，可能需要登录态或受访问限制。")
    return StandardArticle(
        source_name=source_name,
        title=title,
        article_url=article_url,
        content_text=content_text,
        content_html="",
        crawl_source="article_url_analysis",
        raw_payload={"adapter": "direct_wechat_html", "html_length": len(raw)},
    )


def analyze_article_url(session: Session, payload: ArticleAnalyzeRequest) -> ArticleAnalyzeResponse:
    article_url = payload.article_url.strip()
    if not is_valid_wechat_article_url(article_url):
        raise ValueError("请输入有效的微信公众号文章链接。")

    existing = session.scalar(select(Article).where(Article.article_url == article_url))
    before_resource_ids = {resource.id for resource in session.scalars(select(Resource)).all()}
    before_notification_count = session.scalar(select(func.count(Notification.id))) or 0

    exporter_base_url = configured_exporter_base_url(payload.exporter_base_url)
    fallback_message = ""
    try:
        article = fetch_article_from_exporter(article_url, exporter_base_url)
    except RuntimeError as exc:
        fallback_message = str(exc)
        try:
            article = fetch_article_directly_from_wechat(article_url)
        except RuntimeError as direct_exc:
            article = StandardArticle(
                source_name="待识别公众号",
                title="公众号文章链接待补全文",
                article_url=article_url,
                content_text="",
                content_html="",
                crawl_source="article_url_analysis",
                raw_payload={
                    "adapter": "wechat_article_url_fallback",
                    "exporter_error": fallback_message,
                    "direct_error": str(direct_exc),
                },
            )
        else:
            article.raw_payload = {
                **article.raw_payload,
                "exporter_error": fallback_message,
                "fallback": "direct_wechat_html",
            }
        session.add(
            TaskLog(
                id=new_id("task"),
                task_type="article_url_analysis",
                status="partial_success" if article.content_text else "failed",
                summary="exporter 不可用，已尝试直接解析微信页面。" if article.content_text else f"文章链接分析失败：{fallback_message}",
                payload={"article_url": article_url, "base_url": exporter_base_url},
            )
        )
        session.flush()

    result = ingest_standard_articles(
        session,
        [article],
        "article_url_analysis",
        {"article_url": article_url, "base_url": exporter_base_url},
    )

    source = ensure_source(session, article)
    activate_source_tracking(source, "article_url_analysis")
    create_source_subscription(session, source)

    stored = session.scalar(select(Article).where(Article.article_url == article_url))
    if stored:
        stored.source_id = source.id
    session.commit()

    touched_resources = resources_for_article(session, stored.id if stored else None)
    after_notification_count = session.scalar(select(func.count(Notification.id))) or 0
    created = sum(1 for resource in touched_resources if resource.id not in before_resource_ids)
    updated = max(len(touched_resources) - created, 0)
    status = stored.extraction_status if stored else ("skipped" if existing else "failed")
    content_status = stored.content_status if stored else detect_content_status(article)
    message = result.results[0].message if result.results else "文章分析完成。"
    if status == "no_resource":
        message = "文章已获取正文，但未发现明确可追踪资源。"
    if not article.content_text:
        message = "已保存文章链接，但云端未能获取正文。请在本地启动 wechat-article-exporter 后重试，或稍后重新分析。"
    elif fallback_message:
        message = f"{message} 这次使用微信页面直抓备用路径完成。"

    return ArticleAnalyzeResponse(
        article_id=stored.id if stored else None,
        source_id=source.id,
        source_name=source.name,
        article_title=stored.title if stored else article.title,
        article_url=article_url,
        content_status=content_status,
        extraction_status=status,
        tracking_status=source.tracking_status,
        created_resources=created,
        updated_resources=updated,
        notifications_created=max(after_notification_count - before_notification_count, 0),
        resources=[resource_to_analyzed_item(resource, stored.id if stored else None) for resource in touched_resources],
        message=f"{message} 已自动追踪公众号：{source.name}。",
    )


def fetch_missing_fulltext_with_exporter(
    session: Session,
    base_url: str = "",
    limit: int = 30,
) -> HistoryImportResponse:
    base_url = configured_exporter_base_url(base_url)
    articles = (
        session.scalars(
            select(Article)
            .where(Article.content_status.in_(["title_only", "missing_content", "partial_text"]))
            .order_by(Article.imported_at.desc())
            .limit(max(1, min(limit, 100)))
        )
        .unique()
        .all()
    )
    touched_resources: set[str] = set()
    results: list[ImportResultItem] = []
    updated = 0
    failed = 0

    for article in articles:
        try:
            content_text = fetch_text_from_exporter(article.article_url, base_url)
        except RuntimeError as exc:
            failed += 1
            article.extraction_message = f"全文补抓失败：{exc}"
            results.append(
                ImportResultItem(
                    article_url=article.article_url,
                    status="failed",
                    article_id=article.id,
                    message=article.extraction_message,
                )
            )
            continue

        article.content_text = content_text
        article.content_status = detect_content_status(article_to_standard(article))
        clear_article_extraction(session, article)
        standard = article_to_standard(article)
        extracted = extract_resources(standard)
        imported_names: list[str] = []
        for resource_item in extracted:
            resource = upsert_resource_from_extraction(session, resource_item, article)
            touched_resources.add(resource.id)
            imported_names.append(resource.canonical_name)
        article.extraction_status = "success" if imported_names else "no_resource"
        article.extraction_version = EXTRACTION_VERSION
        article.extraction_message = f"通过 wechat-article-exporter 补抓全文并抽取 {len(imported_names)} 个资源。"
        updated += 1
        results.append(
            ImportResultItem(
                article_url=article.article_url,
                status="updated",
                article_id=article.id,
                imported_resources=imported_names,
                message=article.extraction_message,
            )
        )

    for resource_id in touched_resources:
        resource = session.get(Resource, resource_id)
        if resource:
            recalculate_resource_score(session, resource)
            create_subscription_notifications(session, resource)
    pruned_count = prune_orphan_resources(session)

    session.add(
        TaskLog(
            id=new_id("task"),
            task_type="exporter_fulltext_fetch",
            status="success" if failed == 0 else "partial_success",
            summary=f"补抓全文 {len(articles)} 篇，成功 {updated} 篇，失败 {failed} 篇，生成/更新 {len(touched_resources)} 个资源，清理孤儿资源 {pruned_count} 个。",
            payload={"requested_count": len(articles), "base_url": base_url, "limit": limit},
        )
    )
    session.commit()
    return HistoryImportResponse(
        requested_count=len(articles),
        imported_count=updated,
        skipped_count=failed,
        resource_count=len(touched_resources),
        results=results,
    )


def fetch_text_from_exporter(article_url: str, base_url: str = "http://127.0.0.1:4100") -> str:
    endpoint = f"{base_url.rstrip('/')}/api/public/v1/download?url={quote(article_url, safe='')}&format=text"
    request = urllib.request.Request(endpoint, headers={"Accept": "text/plain"})
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                raw = response.read().decode("utf-8", errors="ignore")
            break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(exporter_error_message(last_error, base_url)) from last_error
    text = " ".join(raw.split())
    if len(text) < 120:
        raise RuntimeError("返回内容过短，疑似未拿到正文")
    if any(marker in text for marker in ["环境异常", "访问频率过高", "请在微信客户端打开", "获取全文失败"]):
        raise RuntimeError("微信返回异常页或风控提示")
    return text


def exporter_error_message(error: Exception | None, base_url: str) -> str:
    raw = str(error or "")
    if "10061" in raw or "Connection refused" in raw or "actively refused" in raw:
        return f"全文获取服务未启动：无法连接 {base_url}。请先启动 wechat-article-exporter 后重试。"
    if "timed out" in raw or "timeout" in raw.lower():
        return "全文获取服务响应超时，可能是微信页面加载慢或触发访问限制，请稍后重试。"
    return f"全文获取失败：{raw}"


def prune_orphan_resources(session: Session) -> int:
    resources = session.scalars(
        select(Resource).where(~Resource.id.in_(select(ResourceMention.resource_id)))
    ).all()
    for resource in resources:
        session.execute(delete(ResourceScore).where(ResourceScore.resource_id == resource.id))
        session.execute(delete(StatusCheck).where(StatusCheck.resource_id == resource.id))
        session.delete(resource)
    return len(resources)


def sync_wewe_rss(session: Session, payload: WeweRssSyncRequest) -> HistoryImportResponse:
    config = get_or_create_integration(session, "wewe-rss")
    feed_url = configured_wewe_rss_feed_url(payload.feed_url) or config.feed_url
    if not feed_url:
        raise ValueError("请先配置 wewe-rss 的 JSON/RSS Feed 地址。")
    attempted_urls: list[str] = []
    final_feed_url = feed_url
    if is_local_wewe_rss_feed(feed_url):
        try:
            articles, final_feed_url, attempted_urls = fetch_wewe_rss_articles_with_fallback(feed_url, config.auth_code or None)
        except Exception as exc:
            try:
                articles = fetch_wewe_rss_local_articles()
                final_feed_url = "sqlite://wewe-rss.db"
                attempted_urls = [*attempted_urls, final_feed_url]
            except Exception as local_exc:
                config.status = "sync_failed"
                config.last_message = f"wewe-rss fulltext 同步失败：{exc}；本地 sqlite 兜底也失败：{local_exc}"
                session.add(
                    TaskLog(
                        id=new_id("task"),
                        task_type="wewe_rss_sync",
                        status="failed",
                        summary=config.last_message,
                        payload={"feed_url": feed_url, "attempted_urls": attempted_urls},
                    )
                )
                session.commit()
                raise ValueError(config.last_message) from exc
    else:
        try:
            articles, final_feed_url, attempted_urls = fetch_wewe_rss_articles_with_fallback(feed_url, config.auth_code or None)
        except Exception as exc:
            try:
                articles = fetch_wewe_rss_local_articles()
                final_feed_url = "sqlite://wewe-rss.db"
                attempted_urls = [*attempted_urls, final_feed_url]
            except Exception as local_exc:
                config.status = "sync_failed"
                config.last_message = f"同步失败：{exc}；本地数据库兜底也失败：{local_exc}"
                session.add(
                    TaskLog(
                        id=new_id("task"),
                        task_type="wewe_rss_sync",
                        status="failed",
                        summary=config.last_message,
                        payload={"feed_url": feed_url, "attempted_urls": attempted_urls},
                    )
                )
                session.commit()
                raise ValueError(config.last_message) from exc

    if not articles:
        try:
            articles = fetch_wewe_rss_local_articles()
            final_feed_url = "sqlite://wewe-rss.db"
            attempted_urls = [*attempted_urls, final_feed_url]
        except Exception as local_exc:
            config.status = "sync_failed"
            config.last_message = f"同步失败：未读取到文章；本地数据库兜底也失败：{local_exc}"
            session.add(
                TaskLog(
                    id=new_id("task"),
                    task_type="wewe_rss_sync",
                    status="failed",
                    summary=config.last_message,
                    payload={"feed_url": feed_url, "attempted_urls": attempted_urls},
                )
            )
            session.commit()
            raise ValueError(config.last_message) from local_exc

    result = ingest_standard_articles(
        session,
        articles,
        "wewe_rss_sync",
        {"feed_url": final_feed_url, "configured_feed_url": feed_url, "attempted_urls": attempted_urls},
    )
    config.status = "ok"
    if final_feed_url != feed_url and not final_feed_url.startswith("sqlite://"):
        config.feed_url = final_feed_url
    config.last_message = (
        f"同步完成：读取 {result.requested_count} 篇，"
        f"新增 {result.imported_count} 篇，跳过 {result.skipped_count} 篇，"
        f"生成/更新 {result.resource_count} 个资源。"
        + (
            " HTTP feed 暂不可用，已从本地 wewe-rss 数据库同步文章列表；这些文章需要后续补全文后再做完整资源抽取。"
            if final_feed_url.startswith("sqlite://")
            else f" 原地址不可用，已自动切换到稳定地址：{final_feed_url}"
            if final_feed_url != feed_url
            else ""
        )
    )
    config.last_synced_at = now()
    session.commit()
    return result


def update_source_tracking(session: Session, source_id: str, payload: SourceTrackingRequest) -> SourceRead:
    source = session.get(SourceAccount, source_id)
    if source is None:
        raise ValueError("公众号来源不存在")
    source.tracking_status = payload.tracking_status
    if payload.tracking_status == "active":
        source.first_tracked_at = source.first_tracked_at or now()
        source.next_check_at = source.next_check_at or (now() + SOURCE_CHECK_INTERVAL)
        source.last_check_message = source.last_check_message or "已恢复追踪。"
        create_source_subscription(session, source)
    else:
        source.last_check_message = "已暂停自动追踪。"
        subscription = session.scalar(
            select(Subscription).where(
                Subscription.target_type == "source",
                Subscription.target_value == source.id,
                Subscription.user_id == "default-user",
            )
        )
        if subscription:
            subscription.status = "paused"
    session.commit()
    return source_to_read(session, source)


def check_source_now(session: Session, source_id: str) -> SourceCheckResponse:
    source = session.get(SourceAccount, source_id)
    if source is None:
        raise ValueError("公众号来源不存在")
    timestamp = now()
    if source.last_checked_at and timestamp - source.last_checked_at < SOURCE_CHECK_COOLDOWN:
        remaining = SOURCE_CHECK_COOLDOWN - (timestamp - source.last_checked_at)
        minutes = max(1, int(remaining.total_seconds() // 60) + 1)
        return SourceCheckResponse(
            source_id=source.id,
            status="cooldown",
            message=f"该公众号 30 分钟内已检查过，请约 {minutes} 分钟后再试。",
        )

    source.last_checked_at = timestamp
    source.last_check_status = "running"
    source.last_check_message = "检查任务执行中。"
    session.flush()
    try:
        result = sync_wewe_rss(session, WeweRssSyncRequest())
        source = session.get(SourceAccount, source_id)
        if source:
            source.last_checked_at = timestamp
            source.next_check_at = timestamp + SOURCE_CHECK_INTERVAL
            source.last_check_status = "success"
            source.last_check_message = f"检查完成：新增 {result.imported_count} 篇，跳过 {result.skipped_count} 篇。"
            source.consecutive_failures = 0
            session.commit()
        return SourceCheckResponse(source_id=source_id, status="success", message=source.last_check_message if source else "检查完成。", result=result)
    except Exception as exc:
        source = session.get(SourceAccount, source_id)
        if source:
            source.consecutive_failures += 1
            source.last_check_status = "failed"
            source.last_check_message = f"检查失败：{exc}"
            if source.consecutive_failures >= 3:
                source.tracking_status = "paused"
                source.last_check_message += " 连续失败 3 次，已暂停自动检查。"
            session.add(
                TaskLog(
                    id=new_id("task"),
                    task_type="source_manual_check",
                    status="failed",
                    summary=source.last_check_message,
                    payload={"source_id": source.id, "source_name": source.name},
                )
            )
            session.commit()
        raise ValueError(str(exc)) from exc


def run_due_source_checks(session: Session) -> HistoryImportResponse:
    """Run one low-frequency feed sync for every tracked source due this week.

    wewe-rss exposes a feed for all subscribed accounts, so one feed request is
    both gentler on WeChat and avoids repeating the same crawl for every source.
    """
    timestamp = now()
    due_sources = session.scalars(
        select(SourceAccount)
        .where(
            SourceAccount.tracking_status == "active",
            SourceAccount.next_check_at.is_not(None),
            SourceAccount.next_check_at <= timestamp,
        )
        .order_by(SourceAccount.next_check_at)
    ).all()
    if not due_sources:
        return HistoryImportResponse(requested_count=0, imported_count=0, skipped_count=0, resource_count=0, results=[])

    for source in due_sources:
        source.last_check_status = "running"
        source.last_check_message = "Weekly source check is running."
    session.commit()

    try:
        sync_result = sync_wewe_rss(session, WeweRssSyncRequest())
        # RSS feeds sometimes only contain article metadata. Fetching those
        # entries here preserves the full-text-before-AI extraction contract.
        if sync_result.imported_count:
            fetch_missing_fulltext_with_exporter(
                session,
                base_url=configured_exporter_base_url(),
                limit=min(sync_result.imported_count, 30),
            )
        for source in due_sources:
            source.last_checked_at = timestamp
            source.next_check_at = timestamp + SOURCE_CHECK_INTERVAL
            source.last_check_status = "success"
            source.last_check_message = (
                f"Weekly check completed: {sync_result.imported_count} new articles, "
                f"{sync_result.resource_count} resources created or updated."
            )
            source.consecutive_failures = 0
        session.add(
            TaskLog(
                id=new_id("task"),
                task_type="source_weekly_check",
                status="success",
                summary=f"Checked {len(due_sources)} due sources.",
                payload={"source_ids": [source.id for source in due_sources]},
            )
        )
        session.commit()
        return sync_result
    except Exception as exc:
        for source in due_sources:
            source.consecutive_failures += 1
            source.last_checked_at = timestamp
            source.last_check_status = "failed"
            source.last_check_message = f"Weekly check failed: {exc}"
            if source.consecutive_failures >= 3:
                source.tracking_status = "paused"
                source.last_check_message += " Auto tracking paused after 3 consecutive failures."
        session.add(
            TaskLog(
                id=new_id("task"),
                task_type="source_weekly_check",
                status="failed",
                summary=f"Weekly source check failed: {exc}",
                payload={"source_ids": [source.id for source in due_sources]},
            )
        )
        session.commit()
        raise


def fetch_wewe_rss_articles_with_fallback(feed_url: str, auth_code: str | None) -> tuple[list[StandardArticle], str, list[str]]:
    attempted_urls: list[str] = []
    errors: list[str] = []
    for candidate in wewe_rss_candidate_urls(feed_url):
        attempted_urls.append(candidate)
        try:
            return fetch_wewe_rss_articles(candidate, auth_code), candidate, attempted_urls
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
    raise RuntimeError("；".join(errors))


def is_local_wewe_rss_feed(feed_url: str) -> bool:
    parts = urlsplit(feed_url)
    return parts.hostname in {"127.0.0.1", "localhost"} and parts.port == 4000


def wewe_rss_candidate_urls(feed_url: str) -> list[str]:
    parts = urlsplit(feed_url)
    if not parts.path.endswith(".json"):
        return [feed_url]

    existing_query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "mode" in existing_query or "limit" in existing_query:
        return [feed_url]

    candidates: list[str] = []
    local_fulltext_limits = ["100", "60", "30", "10"] if is_local_wewe_rss_feed(feed_url) else ["10", "5"]
    for mode, limit in [*(("fulltext", limit) for limit in local_fulltext_limits), ("abstract", "30")]:
        query = urlencode({**existing_query, "mode": mode, "limit": limit})
        candidate = urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
        if candidate not in candidates:
            candidates.append(candidate)
    candidates.append(feed_url)
    return candidates


def ingest_standard_articles(
    session: Session,
    articles: list[StandardArticle],
    task_type: str,
    task_payload: dict | None = None,
) -> HistoryImportResponse:
    results: list[ImportResultItem] = []
    imported = 0
    skipped = 0
    touched_resources: set[str] = set()

    for item in articles:
        existing = session.scalar(select(Article).where(Article.article_url == item.article_url))
        if existing and _should_update_existing_article(existing, item):
            _update_existing_article(existing, item)
            source = ensure_source(session, item)
            existing.source_id = source.id
            source.last_synced_at = now()
            clear_article_extraction(session, existing)
            extracted = extract_resources(item)
            imported_names: list[str] = []
            for resource_item in extracted:
                resource = upsert_resource_from_extraction(session, resource_item, existing)
                touched_resources.add(resource.id)
                imported_names.append(resource.canonical_name)
            existing.extraction_status = "success" if imported_names else "no_resource"
            existing.extraction_version = EXTRACTION_VERSION
            existing.extraction_message = extraction_message(detect_content_status(item), len(imported_names), prefix="补全正文后")
            imported += 1
            results.append(
                ImportResultItem(
                    article_url=item.article_url,
                    status="updated",
                    article_id=existing.id,
                    imported_resources=imported_names,
                    message=existing.extraction_message,
                )
            )
            continue
        if existing:
            skipped += 1
            results.append(ImportResultItem(article_url=item.article_url, status="skipped", article_id=existing.id, message="文章已存在"))
            continue

        source = ensure_source(session, item)
        article = Article(
            id=new_id("art"),
            source_id=source.id,
            title=item.title,
            article_url=item.article_url,
            published_at=item.published_at,
            content_text=item.content_text,
            content_html=item.content_html,
            read_count=item.read_count,
            like_count=item.like_count,
            comment_count=item.comment_count,
            crawl_source=item.crawl_source,
            raw_payload=item.raw_payload,
        )
        source.last_synced_at = now()
        session.add(article)
        session.flush()
        article.content_status = detect_content_status(item)
        article.extraction_status = "pending"
        article.extraction_version = EXTRACTION_VERSION

        extracted = extract_resources(item)
        imported_names: list[str] = []
        for resource_item in extracted:
            resource = upsert_resource_from_extraction(session, resource_item, article)
            touched_resources.add(resource.id)
            imported_names.append(resource.canonical_name)
        article.extraction_status = "success" if imported_names else "no_resource"
        article.extraction_message = extraction_message(article.content_status, len(imported_names))

        imported += 1
        results.append(
            ImportResultItem(
                article_url=item.article_url,
                status="imported",
                article_id=article.id,
                imported_resources=imported_names,
                message=article.extraction_message,
            )
        )

    for resource_id in touched_resources:
        resource = session.get(Resource, resource_id)
        if resource:
            recalculate_resource_score(session, resource)
            create_subscription_notifications(session, resource)

    content_counts = content_status_counts(articles)
    session.add(
        TaskLog(
            id=new_id("task"),
            task_type=task_type,
            status="success",
            summary=(
                f"读取 {len(articles)} 篇文章，新增 {imported} 篇，跳过 {skipped} 篇；"
                f"全文 {content_counts.get('full_text', 0)} 篇，标题/缺正文 {content_counts.get('title_only', 0) + content_counts.get('missing_content', 0)} 篇。"
            ),
            payload={"requested_count": len(articles), "content_status_counts": content_counts, **(task_payload or {})},
        )
    )
    session.commit()
    return HistoryImportResponse(
        requested_count=len(articles),
        imported_count=imported,
        skipped_count=skipped,
        resource_count=len(touched_resources),
        results=results,
    )


def content_status_counts(articles: list[StandardArticle]) -> dict[str, int]:
    counts: dict[str, int] = {"full_text": 0, "partial_text": 0, "title_only": 0, "missing_content": 0}
    for item in articles:
        status = detect_content_status(item)
        counts[status] = counts.get(status, 0) + 1
    return counts


def extraction_message(content_status: str, imported_count: int, prefix: str = "") -> str:
    if content_status in {"title_only", "missing_content"}:
        lead = f"{prefix}，" if prefix else ""
        return f"{lead}仅导入文章列表，缺少正文，已跳过资源解析。请先用 wechat-article-exporter 抓取正文后再导入。"
    if content_status == "partial_text":
        return f"{prefix}抽取 {imported_count} 个资源；正文较短，建议人工复核。"
    return f"{prefix}抽取 {imported_count} 个资源。"


def _should_update_existing_article(existing: Article, item: StandardArticle) -> bool:
    old_text_len = len((existing.content_text or "").strip())
    new_text_len = len((item.content_text or "").strip())
    old_html_len = len((existing.content_html or "").strip())
    new_html_len = len((item.content_html or "").strip())
    return new_text_len > max(old_text_len + 80, old_text_len * 1.4) or new_html_len > max(old_html_len + 200, old_html_len * 1.4)


def _update_existing_article(existing: Article, item: StandardArticle) -> None:
    existing.title = item.title or existing.title
    existing.published_at = item.published_at or existing.published_at
    existing.content_text = item.content_text or existing.content_text
    existing.content_html = item.content_html or existing.content_html
    existing.content_status = detect_content_status(item)
    existing.read_count = item.read_count if item.read_count is not None else existing.read_count
    existing.like_count = item.like_count if item.like_count is not None else existing.like_count
    existing.comment_count = item.comment_count if item.comment_count is not None else existing.comment_count
    existing.crawl_source = item.crawl_source or existing.crawl_source
    existing.raw_payload = item.raw_payload or existing.raw_payload


def clear_article_extraction(session: Session, article: Article) -> None:
    mentions = session.scalars(select(ResourceMention).where(ResourceMention.article_id == article.id)).all()
    affected_resource_ids = {mention.resource_id for mention in mentions}
    for mention in mentions:
        session.delete(mention)
    session.flush()
    for resource_id in affected_resource_ids:
        remaining = session.scalar(select(func.count(ResourceMention.id)).where(ResourceMention.resource_id == resource_id)) or 0
        if remaining == 0:
            resource = session.get(Resource, resource_id)
            if resource:
                session.execute(delete(ResourceScore).where(ResourceScore.resource_id == resource.id))
                session.execute(delete(StatusCheck).where(StatusCheck.resource_id == resource.id))
                session.delete(resource)
    article.extraction_status = "pending"
    article.extraction_message = ""
    session.flush()


def upsert_resource_from_extraction(session: Session, item: ExtractedResource, article: Article) -> Resource:
    key = canonical_key(item.name)
    resource = None
    for candidate in session.scalars(select(Resource)):
        keys = {canonical_key(candidate.canonical_name), *(canonical_key(alias) for alias in candidate.aliases)}
        if key in keys or set(candidate.links).intersection(item.links):
            resource = candidate
            break

    if resource is None:
        resource = Resource(
            id=new_id("res"),
            canonical_name=item.name,
            aliases=item.aliases,
            resource_type=item.resource_type,
            platforms=item.platforms,
            capability_tags=item.capability_tags,
            summary=item.summary,
            links=item.links,
            current_status="review" if item.confidence < 0.7 else "available",
            risk_level=item.risk_level,
            risk_notes=item.risk_notes,
            last_mentioned_at=article.published_at or now(),
        )
        session.add(resource)
        session.flush()
    else:
        if item.name not in resource.aliases and canonical_key(item.name) != canonical_key(resource.canonical_name):
            resource.aliases = [*resource.aliases, item.name]
        resource.aliases = sorted(set(resource.aliases).union(item.aliases))
        resource.links = sorted(set(resource.links).union(item.links))
        resource.platforms = sorted(set(resource.platforms).union(item.platforms))
        resource.capability_tags = sorted(set(resource.capability_tags).union(item.capability_tags))
        if len(item.summary) > len(resource.summary):
            resource.summary = item.summary
        if item.risk_level != "low":
            resource.risk_level = item.risk_level
            resource.risk_notes = item.risk_notes
        if article.published_at and (resource.last_mentioned_at is None or article.published_at > resource.last_mentioned_at):
            resource.last_mentioned_at = article.published_at
        apply_semantic_status_change(session, resource, item, article)

    mention = session.scalar(
        select(ResourceMention).where(
            ResourceMention.resource_id == resource.id,
            ResourceMention.article_id == article.id,
            ResourceMention.evidence_snippet == item.evidence_snippet,
        )
    )
    if mention is None:
        mention = ResourceMention(
            id=new_id("men"),
            resource_id=resource.id,
            article_id=article.id,
            evidence_snippet=item.evidence_snippet,
            confidence=item.confidence,
            extracted_name=item.name,
            match_keywords=item.capability_tags,
        )
        session.add(mention)
    apply_semantic_status_change(session, resource, item, article)
    if not resource.status_checks:
        session.add(
            StatusCheck(
                id=new_id("chk"),
                resource_id=resource.id,
                target_url=item.links[0] if item.links else "",
                result_status=resource.current_status,
                change_summary="首次发现资源，状态来自入库初检。",
                suggestion="继续观察" if resource.current_status == "available" else "进入人工复核",
                check_source="initial_ingest",
            )
        )
    session.flush()
    return resource


def apply_semantic_status_change(session: Session, resource: Resource, item: ExtractedResource, article: Article) -> None:
    text = f"{article.title}\n{article.content_text}\n{item.evidence_snippet}"
    change_status = ""
    change_summary = ""
    suggestion = "继续观察"
    if any(word in text for word in ["失效", "下架", "不能用", "无法使用", "跑路", "链接挂了", "地址失效"]):
        change_status = "suspected_down"
        change_summary = f"{resource.canonical_name} 在文章中出现疑似失效线索。"
        suggestion = "进入人工复核，等待后续公众号证据确认。"
    elif any(word in text for word in ["恢复", "复活", "重新可用", "又能用"]):
        change_status = "available"
        change_summary = f"{resource.canonical_name} 在文章中出现恢复可用线索。"
    elif any(word in text for word in ["新版", "新版本", "更新", "换地址", "最新地址", "替代", "新功能"]):
        change_status = "suspected_update"
        change_summary = f"{resource.canonical_name} 在文章中出现更新或地址变化线索。"
        suggestion = "查看证据片段并确认是否需要更新资源说明。"

    if not change_status:
        return
    latest = session.scalar(
        select(StatusCheck)
        .where(StatusCheck.resource_id == resource.id, StatusCheck.result_status == change_status, StatusCheck.change_summary == change_summary)
        .order_by(StatusCheck.checked_at.desc())
    )
    if latest:
        return
    resource.current_status = change_status
    session.add(
        StatusCheck(
            id=new_id("chk"),
            resource_id=resource.id,
            target_url=item.links[0] if item.links else "",
            result_status=change_status,
            change_summary=change_summary,
            suggestion=suggestion,
            check_source="article_semantic_analysis",
        )
    )


def resources_for_article(session: Session, article_id: str | None) -> list[Resource]:
    if not article_id:
        return []
    mentions = session.scalars(select(ResourceMention).where(ResourceMention.article_id == article_id)).all()
    resources = {mention.resource.id: mention.resource for mention in mentions}
    return sorted(resources.values(), key=lambda item: item.latest_score, reverse=True)


def resource_to_analyzed_item(resource: Resource, article_id: str | None = None) -> AnalyzedResource:
    evidence = ""
    if article_id:
        mention = next((item for item in resource.mentions if item.article_id == article_id), None)
        evidence = mention.evidence_snippet if mention else ""
    return AnalyzedResource(
        id=resource.id,
        canonical_name=resource.canonical_name,
        latest_score=resource.latest_score,
        latest_grade=resource.latest_grade,
        current_status=resource.current_status,
        risk_level=resource.risk_level,
        summary=resource.summary,
        evidence_snippet=evidence,
    )


def _legacy_search_resources(session: Session, query: str) -> SearchResponse:
    q = query.strip()
    if not q:
        return SearchResponse(query=query, total=0, items=[], message="请输入关键词。")

    pattern = f"%{q}%"
    resources = list(
        session.scalars(
            select(Resource)
            .where(or_(Resource.canonical_name.like(pattern), Resource.summary.like(pattern), Resource.resource_type.like(pattern)))
            .order_by(Resource.latest_score.desc(), Resource.last_mentioned_at.desc())
        )
    )

    if not resources:
        mention_matches = session.scalars(select(ResourceMention).where(ResourceMention.evidence_snippet.like(pattern))).all()
        resources = sorted({mention.resource for mention in mention_matches}, key=lambda item: item.latest_score, reverse=True)

    items = [resource_to_search_item(resource) for resource in resources]
    message = "当前资源库暂无相关资源，可订阅该关键词，后续有结果时提醒你。" if not items else f"找到 {len(items)} 个资源。"
    return SearchResponse(query=query, total=len(items), items=items, message=message)


def search_resources(session: Session, query: str) -> SearchResponse:
    q = query.strip()
    if not q:
        return SearchResponse(query=query, total=0, items=[], message="请输入关键词。")

    scored: list[tuple[Resource, int, str]] = []
    for resource in session.scalars(select(Resource)).all():
        score, reason = _match_resource(resource, q)
        if score > 0:
            scored.append((resource, score, reason))
    scored.sort(key=lambda item: (item[1], item[0].latest_score, item[0].last_mentioned_at or datetime.min), reverse=True)

    items = [resource_to_search_item(resource, match_reason=reason) for resource, _, reason in scored]
    message = "当前资源库暂无相关资源，可订阅该关键词，后续有结果时提醒你。" if not items else f"找到 {len(items)} 个资源。"
    return SearchResponse(query=query, total=len(items), items=items, message=message)


def _match_resource(resource: Resource, query: str) -> tuple[int, str]:
    q = query.lower()
    score = 0
    reasons: list[str] = []
    searchable_parts = [
        resource.canonical_name,
        *(resource.aliases or []),
        *(resource.capability_tags or []),
        resource.summary or "",
        resource.resource_type or "",
    ]
    for mention in resource.mentions:
        searchable_parts.append(mention.evidence_snippet or "")
        searchable_parts.extend(mention.match_keywords or [])
    searchable_text = " ".join(searchable_parts).lower()

    if q in resource.canonical_name.lower():
        score += 120
        reasons.append(f"资源名命中：{resource.canonical_name}")
    for alias in resource.aliases or []:
        if q in alias.lower():
            score += 100
            reasons.append(f"别名命中：{alias}")
            break
    for tag in resource.capability_tags or []:
        if _query_matches_term(q, tag.lower()):
            score += 90
            reasons.append(f"能力标签命中：{tag}")
            break
    if q in (resource.summary or "").lower():
        score += 50
        reasons.append("简介命中")
    if q == (resource.resource_type or "").lower():
        score += 20
        reasons.append(f"类型命中：{resource.resource_type}")
    for mention in resource.mentions:
        if q in (mention.evidence_snippet or "").lower():
            score += 60
            reasons.append(f"证据命中：{mention.evidence_snippet[:48]}")
            break
        for keyword in mention.match_keywords or []:
            if _query_matches_term(q, keyword.lower()):
                score += 70
                reasons.append(f"证据标签命中：{keyword}")
                break
    semantic_score, semantic_reason = _semantic_query_match(q, searchable_text)
    if semantic_score:
        score += semantic_score
        reasons.append(semantic_reason)
    return score, "；".join(reasons[:2])


GENERIC_REVERSE_MATCH_TERMS = {
    "app",
    "ios",
    "pc",
    "安卓",
    "免费",
    "开源",
    "软件",
    "工具",
    "神器",
    "下载",
    "网站",
    "平台",
    "资源",
    "合集",
}

MUSIC_QUERY_TERMS = ["听歌", "音乐", "歌曲", "播放器", "歌单"]
MUSIC_RESOURCE_TERMS = ["音乐", "歌曲", "听歌", "播放器", "歌单", "歌词", "无损", "音源"]


def _query_matches_term(query: str, term: str) -> bool:
    if not term:
        return False
    if query in term:
        return True
    if term in GENERIC_REVERSE_MATCH_TERMS:
        return False
    if len(term) < 3:
        return False
    return term in query


def _semantic_query_match(query: str, searchable_text: str) -> tuple[int, str]:
    if any(term in query for term in MUSIC_QUERY_TERMS) and any(term in searchable_text for term in MUSIC_RESOURCE_TERMS):
        return 80, "语义命中：音乐/听歌能力"
    return 0, ""


def list_admin_resources(
    session: Session,
    q: str = "",
    status: str = "",
    risk: str = "",
    page: int = 1,
    page_size: int = 50,
) -> AdminResourceListResponse:
    query = select(Resource)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Resource.canonical_name.like(pattern),
                Resource.summary.like(pattern),
                Resource.resource_type.like(pattern),
            )
        )
    if status:
        query = query.where(Resource.current_status == status)
    if risk:
        query = query.where(Resource.risk_level == risk)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = max(page - 1, 0) * page_size
    resources = session.scalars(
        query.order_by(Resource.latest_score.desc(), Resource.updated_at.desc()).offset(offset).limit(page_size)
    ).all()
    return AdminResourceListResponse(total=total, items=[resource_to_search_item(resource) for resource in resources])


def delete_resource(session: Session, resource_id: str) -> ResourceBulkActionResponse:
    return delete_resources(session, [resource_id])


def delete_resources(session: Session, resource_ids: list[str]) -> ResourceBulkActionResponse:
    unique_ids = _unique([resource_id.strip() for resource_id in resource_ids if resource_id.strip()])
    deleted = 0
    for resource_id in unique_ids:
        resource = session.get(Resource, resource_id)
        if resource is None:
            continue
        _delete_resource_graph(session, resource)
        deleted += 1
    session.commit()
    return ResourceBulkActionResponse(
        requested_count=len(unique_ids),
        deleted_count=deleted,
        skipped_count=max(len(unique_ids) - deleted, 0),
        message=f"已删除 {deleted} 个资源。",
    )


def bulk_update_resources(session: Session, payload: ResourceBulkUpdateRequest) -> ResourceBulkActionResponse:
    unique_ids = _unique([resource_id.strip() for resource_id in payload.resource_ids if resource_id.strip()])
    updated = 0
    for resource_id in unique_ids:
        resource = session.get(Resource, resource_id)
        if resource is None:
            continue
        before = {
            "current_status": resource.current_status,
            "risk_level": resource.risk_level,
        }
        if payload.current_status:
            resource.current_status = payload.current_status
        if payload.risk_level:
            resource.risk_level = payload.risk_level
        session.add(
            ManualReview(
                id=new_id("rev"),
                target_type="resource",
                target_id=resource.id,
                action_type="bulk_update",
                before_value=before,
                after_value={"current_status": resource.current_status, "risk_level": resource.risk_level},
                note=payload.note,
            )
        )
        recalculate_resource_score(session, resource)
        updated += 1
    session.commit()
    return ResourceBulkActionResponse(
        requested_count=len(unique_ids),
        updated_count=updated,
        skipped_count=max(len(unique_ids) - updated, 0),
        message=f"已更新 {updated} 个资源。",
    )


def _delete_resource_graph(session: Session, resource: Resource) -> None:
    session.execute(delete(ResourceMention).where(ResourceMention.resource_id == resource.id))
    session.execute(delete(ResourceScore).where(ResourceScore.resource_id == resource.id))
    session.execute(delete(StatusCheck).where(StatusCheck.resource_id == resource.id))
    session.execute(delete(Notification).where(Notification.resource_id == resource.id))
    session.execute(delete(ManualReview).where(ManualReview.target_type == "resource", ManualReview.target_id == resource.id))
    session.delete(resource)


def resource_to_search_item(resource: Resource, match_reason: str = "") -> SearchResource:
    latest_score = resource.scores[-1] if resource.scores else None
    source_count = len({mention.article.source_id for mention in resource.mentions})
    return SearchResource(
        id=resource.id,
        canonical_name=resource.canonical_name,
        resource_type=resource.resource_type,
        capability_tags=resource.capability_tags or [],
        summary=resource.summary,
        current_status=resource.current_status,
        risk_level=resource.risk_level,
        latest_score=resource.latest_score,
        latest_grade=resource.latest_grade,
        source_count=source_count,
        mention_count=len(resource.mentions),
        last_mentioned_at=resource.last_mentioned_at,
        explanation=latest_score.explanation if latest_score else "等待评分。",
        match_reason=match_reason,
    )


def get_resource_detail(session: Session, resource_id: str) -> ResourceDetail | None:
    resource = session.get(Resource, resource_id)
    if resource is None:
        return None
    if not resource.scores:
        score = recalculate_resource_score(session, resource)
        session.commit()
    else:
        score = resource.scores[-1]

    sources = [
        SourceEvidence(
            source_name=mention.article.source.name,
            source_trust_level=mention.article.source.trust_level,
            article_title=mention.article.title,
            article_url=mention.article.article_url,
            published_at=mention.article.published_at,
            evidence_snippet=mention.evidence_snippet,
            confidence=mention.confidence,
        )
        for mention in sorted(resource.mentions, key=lambda item: item.article.published_at or datetime.min, reverse=True)
    ]
    timeline = [
        StatusTimelineItem(
            checked_at=check.checked_at,
            target_url=check.target_url,
            result_status=check.result_status,
            change_summary=check.change_summary,
            suggestion=check.suggestion,
        )
        for check in sorted(resource.status_checks, key=lambda item: item.checked_at, reverse=True)
    ]
    return ResourceDetail(
        id=resource.id,
        canonical_name=resource.canonical_name,
        aliases=resource.aliases,
        resource_type=resource.resource_type,
        platforms=resource.platforms,
        capability_tags=resource.capability_tags or [],
        summary=resource.summary,
        links=resource.links,
        current_status=resource.current_status,
        risk_level=resource.risk_level,
        risk_notes=resource.risk_notes,
        score=score_to_schema(score),
        sources=sources,
        timeline=timeline,
    )


def score_to_schema(score) -> ScoreBreakdown:
    return ScoreBreakdown(
        total_score=score.total_score,
        grade=score.grade,
        multi_source_score=score.multi_source_score,
        source_trust_score=score.source_trust_score,
        interaction_score=score.interaction_score,
        freshness_score=score.freshness_score,
        availability_score=score.availability_score,
        evidence_score=score.evidence_score,
        risk_penalty=score.risk_penalty,
        explanation=score.explanation,
    )


def create_subscription(session: Session, payload: SubscriptionCreate) -> SubscriptionRead:
    display = payload.display_name or payload.target_value
    existing = session.scalar(
        select(Subscription).where(
            Subscription.user_id == "default-user",
            Subscription.target_type == payload.target_type,
            Subscription.target_value == payload.target_value,
        )
    )
    if existing:
        return subscription_to_schema(existing)
    sub = Subscription(
        id=new_id("sub"),
        target_type=payload.target_type,
        target_value=payload.target_value,
        display_name=display,
    )
    session.add(sub)
    session.commit()
    return subscription_to_schema(sub)


def list_subscriptions(session: Session) -> list[SubscriptionRead]:
    return [subscription_to_schema(item) for item in session.scalars(select(Subscription).order_by(Subscription.created_at.desc()))]


def subscription_to_schema(item: Subscription) -> SubscriptionRead:
    return SubscriptionRead(
        id=item.id,
        target_type=item.target_type,
        target_value=item.target_value,
        display_name=item.display_name,
        status=item.status,
        created_at=item.created_at,
    )


def create_source_subscription(session: Session, source: SourceAccount) -> Subscription:
    existing = session.scalar(
        select(Subscription).where(
            Subscription.user_id == "default-user",
            Subscription.target_type == "source",
            Subscription.target_value == source.id,
        )
    )
    if existing:
        existing.status = "active"
        existing.display_name = source.name
        return existing
    subscription = Subscription(
        id=new_id("sub"),
        target_type="source",
        target_value=source.id,
        display_name=source.name,
        status="active",
    )
    session.add(subscription)
    session.flush()
    return subscription


def create_subscription_notifications(session: Session, resource: Resource) -> int:
    subscriptions = session.scalars(select(Subscription).where(Subscription.status == "active")).all()
    created = 0
    for sub in subscriptions:
        matched = False
        if sub.target_type == "resource" and sub.target_value == resource.id:
            matched = True
        if sub.target_type == "source" and any(mention.article.source_id == sub.target_value for mention in resource.mentions):
            matched = True
        if sub.target_type == "topic" and (
            sub.target_value.lower() in resource.canonical_name.lower()
            or sub.target_value.lower() in resource.summary.lower()
            or sub.target_value.lower() == resource.resource_type.lower()
            or any(sub.target_value.lower() in tag.lower() or tag.lower() in sub.target_value.lower() for tag in resource.capability_tags or [])
        ):
            matched = True
        if not matched:
            continue
        existing = session.scalar(
            select(Notification).where(
                Notification.subscription_id == sub.id,
                Notification.resource_id == resource.id,
                Notification.event_type == "resource_matched",
                Notification.title == f"{sub.display_name} 有新资源：{resource.canonical_name}",
            )
        )
        if existing:
            continue
        session.add(
            Notification(
                id=new_id("noti"),
                subscription_id=sub.id,
                event_type="resource_matched",
                title=f"{sub.display_name} 有新资源：{resource.canonical_name}",
                body=f"{resource.canonical_name} 当前评分 {resource.latest_score:.1f}/{resource.latest_grade}，状态 {resource.current_status}。",
                resource_id=resource.id,
            )
        )
        created += 1
    return created


def list_notifications(session: Session) -> list[NotificationRead]:
    items = session.scalars(select(Notification).order_by(Notification.created_at.desc())).all()
    return [
        NotificationRead(
            id=item.id,
            event_type=item.event_type,
            title=item.title,
            body=item.body,
            resource_id=item.resource_id,
            channel=item.channel,
            status=item.status,
            created_at=item.created_at,
        )
        for item in items
    ]


def upsert_feishu_setting(session: Session, webhook_url: str) -> FeishuSettingRead:
    setting = get_or_create_setting(session)
    setting.feishu_webhook = webhook_url
    setting.feishu_status = "configured"
    setting.last_test_result = "未测试"
    session.commit()
    return feishu_setting_to_schema(setting)


def test_feishu_setting(session: Session, webhook_url: str | None = None) -> FeishuSettingRead:
    setting = get_or_create_setting(session)
    url = webhook_url or setting.feishu_webhook
    if not url.startswith("https://") or "feishu" not in url and "larksuite" not in url:
        setting.feishu_status = "test_failed"
        setting.last_test_result = "请输入有效的飞书 Webhook 地址。"
    else:
        setting.feishu_webhook = url
        setting.feishu_status = "configured"
        setting.last_test_result = "测试通过：MVP 当前记录测试结果，不实际发送网络请求。"
    setting.last_tested_at = now()
    session.commit()
    return feishu_setting_to_schema(setting)


def get_or_create_setting(session: Session) -> NotificationSetting:
    setting = session.scalar(select(NotificationSetting).where(NotificationSetting.user_id == "default-user"))
    if setting:
        return setting
    setting = NotificationSetting(id=new_id("set"), user_id="default-user")
    session.add(setting)
    session.flush()
    return setting


def get_feishu_setting(session: Session) -> FeishuSettingRead:
    return feishu_setting_to_schema(get_or_create_setting(session))


def feishu_setting_to_schema(setting: NotificationSetting) -> FeishuSettingRead:
    return FeishuSettingRead(
        status=setting.feishu_status,
        masked_webhook=mask_webhook(setting.feishu_webhook),
        last_test_result=setting.last_test_result,
        last_tested_at=setting.last_tested_at,
    )


def is_valid_feishu_webhook(url: str) -> bool:
    clean = (url or "").strip()
    return clean.startswith("https://") and "/bot/v2/hook/" in clean and ("feishu" in clean or "larksuite" in clean)


def send_feishu_message(webhook_url: str, title: str, body: str) -> tuple[bool, str]:
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body}}],
        },
    }
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if 200 <= response.status < 300:
                return True, f"飞书消息已发送：HTTP {response.status}"
            return False, f"飞书发送失败：HTTP {response.status} {raw[:180]}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return False, f"飞书发送失败：{exc}"


def send_feishu_notification_if_configured(session: Session, title: str, body: str) -> None:
    setting = get_or_create_setting(session)
    if not is_valid_feishu_webhook(setting.feishu_webhook):
        return
    ok, message = send_feishu_message(setting.feishu_webhook, title=title, body=body)
    setting.feishu_status = "configured" if ok else "send_failed"
    setting.last_test_result = message
    setting.last_tested_at = now()


def upsert_feishu_setting(session: Session, webhook_url: str) -> FeishuSettingRead:
    setting = get_or_create_setting(session)
    if not is_valid_feishu_webhook(webhook_url):
        setting.feishu_status = "invalid"
        setting.last_test_result = "请输入有效的飞书或 Lark 自定义机器人 Webhook。"
        session.commit()
        return feishu_setting_to_schema(setting)
    setting.feishu_webhook = webhook_url.strip()
    setting.feishu_status = "configured"
    setting.last_test_result = "已保存，尚未发送测试消息。"
    session.commit()
    return feishu_setting_to_schema(setting)


def test_feishu_setting(session: Session, webhook_url: str | None = None) -> FeishuSettingRead:
    setting = get_or_create_setting(session)
    url = (webhook_url or setting.feishu_webhook or "").strip()
    if not is_valid_feishu_webhook(url):
        setting.feishu_status = "test_failed"
        setting.last_test_result = "请输入有效的飞书或 Lark 自定义机器人 Webhook。"
    else:
        setting.feishu_webhook = url
        ok, message = send_feishu_message(
            url,
            title="公众号资源发现与追踪助手测试通知",
            body="这是一条真实飞书 Webhook 测试消息。收到后说明通知链路已打通。",
        )
        setting.feishu_status = "configured" if ok else "test_failed"
        setting.last_test_result = message
    setting.last_tested_at = now()
    session.commit()
    return feishu_setting_to_schema(setting)


def create_subscription_notifications(session: Session, resource: Resource) -> int:
    subscriptions = session.scalars(select(Subscription).where(Subscription.status == "active")).all()
    created = 0
    for sub in subscriptions:
        matched = False
        if sub.target_type == "resource" and sub.target_value == resource.id:
            matched = True
        if sub.target_type == "source" and any(mention.article.source_id == sub.target_value for mention in resource.mentions):
            matched = True
        if sub.target_type == "topic" and (
            sub.target_value.lower() in resource.canonical_name.lower()
            or sub.target_value.lower() in resource.summary.lower()
            or sub.target_value.lower() == resource.resource_type.lower()
            or any(sub.target_value.lower() in tag.lower() or tag.lower() in sub.target_value.lower() for tag in resource.capability_tags or [])
        ):
            matched = True
        if not matched:
            continue
        title = f"{sub.display_name} 有新资源：{resource.canonical_name}"
        body = f"{resource.canonical_name} 当前评分 {resource.latest_score:.1f}/{resource.latest_grade}，状态 {resource.current_status}。"
        existing = session.scalar(
            select(Notification).where(
                Notification.subscription_id == sub.id,
                Notification.resource_id == resource.id,
                Notification.event_type == "resource_matched",
                Notification.title == title,
            )
        )
        if existing:
            continue
        session.add(
            Notification(
                id=new_id("noti"),
                subscription_id=sub.id,
                event_type="resource_matched",
                title=title,
                body=body,
                resource_id=resource.id,
            )
        )
        send_feishu_notification_if_configured(session, title, body)
        created += 1
    return created


def apply_manual_review(session: Session, resource_id: str, payload: ManualReviewRequest) -> ManualReviewResponse:
    resource = session.get(Resource, resource_id)
    if resource is None:
        raise ValueError("资源不存在")
    before = {
        "canonical_name": resource.canonical_name,
        "summary": resource.summary,
        "current_status": resource.current_status,
        "risk_level": resource.risk_level,
        "risk_notes": resource.risk_notes,
        "links": resource.links,
    }
    for field in ["canonical_name", "summary", "current_status", "risk_level", "risk_notes", "links"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(resource, field, value)
    review = ManualReview(
        id=new_id("rev"),
        target_type="resource",
        target_id=resource.id,
        action_type="manual_update",
        before_value=before,
        after_value={
            "canonical_name": resource.canonical_name,
            "summary": resource.summary,
            "current_status": resource.current_status,
            "risk_level": resource.risk_level,
            "risk_notes": resource.risk_notes,
            "links": resource.links,
        },
        note=payload.note,
    )
    session.add(review)
    score = recalculate_resource_score(session, resource)
    session.commit()
    return ManualReviewResponse(resource_id=resource.id, review_id=review.id, score=score_to_schema(score))


def recalculate_score_by_id(session: Session, resource_id: str) -> ScoreBreakdown:
    resource = session.get(Resource, resource_id)
    if resource is None:
        raise ValueError("资源不存在")
    score = recalculate_resource_score(session, resource)
    session.commit()
    return score_to_schema(score)


def reparse_all_articles(session: Session) -> HistoryImportResponse:
    articles = session.scalars(select(Article).order_by(Article.imported_at)).all()
    touched_resources: set[str] = set()
    results: list[ImportResultItem] = []
    for article in articles:
        clear_article_extraction(session, article)
        standard = article_to_standard(article)
        extracted = extract_resources(standard)
        imported_names: list[str] = []
        for resource_item in extracted:
            resource = upsert_resource_from_extraction(session, resource_item, article)
            touched_resources.add(resource.id)
            imported_names.append(resource.canonical_name)
        article.content_status = detect_content_status(standard)
        article.extraction_status = "success" if imported_names else "no_resource"
        article.extraction_version = EXTRACTION_VERSION
        article.extraction_message = extraction_message(article.content_status, len(imported_names), prefix="重新解析")
        results.append(
            ImportResultItem(
                article_url=article.article_url,
                status="reparsed",
                article_id=article.id,
                imported_resources=imported_names,
                message=article.extraction_message,
            )
        )

    for resource_id in touched_resources:
        resource = session.get(Resource, resource_id)
        if resource:
            recalculate_resource_score(session, resource)
            create_subscription_notifications(session, resource)
    pruned_count = prune_orphan_resources(session)

    session.add(
        TaskLog(
            id=new_id("task"),
            task_type="reparse_all_articles",
            status="success",
            summary=f"重新解析 {len(articles)} 篇文章，生成/更新 {len(touched_resources)} 个资源，清理孤儿资源 {pruned_count} 个。",
            payload={"requested_count": len(articles), "extraction_version": EXTRACTION_VERSION},
        )
    )
    session.commit()
    return HistoryImportResponse(
        requested_count=len(articles),
        imported_count=len(articles),
        skipped_count=0,
        resource_count=len(touched_resources),
        results=results,
    )


def article_to_standard(article: Article) -> StandardArticle:
    return StandardArticle(
        source_name=article.source.name,
        source_identifier=article.source.source_identifier,
        title=article.title,
        article_url=article.article_url,
        published_at=article.published_at,
        content_text=article.content_text or "",
        content_html=article.content_html or "",
        read_count=article.read_count,
        like_count=article.like_count,
        comment_count=article.comment_count,
        crawl_source=article.crawl_source,
        raw_payload=article.raw_payload or {},
    )


def admin_overview(session: Session) -> AdminOverview:
    latest_task = session.scalar(select(TaskLog).order_by(TaskLog.created_at.desc()))
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    database_label = str(DB_FILE) if DB_FILE is not None else DATABASE_URL.split("@")[-1]
    return AdminOverview(
        source_count=session.scalar(select(func.count(SourceAccount.id))) or 0,
        article_count=session.scalar(select(func.count(Article.id))) or 0,
        resource_count=session.scalar(select(func.count(Resource.id))) or 0,
        subscription_count=session.scalar(select(func.count(Subscription.id))) or 0,
        notification_count=session.scalar(select(func.count(Notification.id))) or 0,
        pending_review_count=session.scalar(select(func.count(Resource.id)).where(Resource.current_status == "review")) or 0,
        latest_task_summary=latest_task.summary if latest_task else "",
        database_path=database_label,
        today_analyzed_count=session.scalar(
            select(func.count(TaskLog.id)).where(TaskLog.task_type == "article_url_analysis", TaskLog.created_at >= today_start)
        )
        or 0,
        fulltext_success_count=session.scalar(select(func.count(Article.id)).where(Article.content_status == "full_text")) or 0,
        extraction_success_count=session.scalar(select(func.count(Article.id)).where(Article.extraction_status == "success")) or 0,
        tracked_source_count=session.scalar(select(func.count(SourceAccount.id)).where(SourceAccount.tracking_status == "active")) or 0,
        due_check_count=session.scalar(
            select(func.count(SourceAccount.id)).where(SourceAccount.tracking_status == "active", SourceAccount.next_check_at <= now())
        )
        or 0,
        ai_status=ai_extractor_status(),
    )


def ai_extractor_status() -> str:
    enabled = os.getenv("RESOURCE_EXTRACTOR_LLM_ENABLED", "auto").lower()
    if enabled in {"0", "false", "off", "no"}:
        return "disabled"
    if os.getenv("RESOURCE_EXTRACTOR_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"):
        return "enabled"
    return "not_configured"


def list_task_logs(session: Session, limit: int = 20) -> list[TaskLogRead]:
    tasks = session.scalars(select(TaskLog).order_by(TaskLog.created_at.desc()).limit(limit)).all()
    return [
        TaskLogRead(
            id=task.id,
            task_type=task.task_type,
            status=task.status,
            summary=task.summary,
            payload=task.payload,
            created_at=task.created_at,
        )
        for task in tasks
    ]


def get_or_create_integration(session: Session, provider: str) -> IntegrationConfig:
    config = session.scalar(select(IntegrationConfig).where(IntegrationConfig.provider == provider))
    if config:
        return config
    defaults = {
        "wechat-article-exporter": {
            "base_url": configured_exporter_base_url(),
            "status": "configured",
            "last_message": "已从 GitHub 拉取源码；用于历史冷启动导出，再导入本系统。",
        },
        "wewe-rss": {
            "base_url": os.getenv("WEWE_RSS_BASE_URL", "http://127.0.0.1:4000"),
            "feed_url": configured_wewe_rss_feed_url() or "http://127.0.0.1:4000/feeds/all.json",
            "auth_code": os.getenv("WEWE_RSS_AUTH_CODE", ""),
            "status": "configured",
            "last_message": "已配置本地 wewe-rss 默认地址；扫码登录并添加公众号后可同步。",
        },
        "supplement-import": {
            "status": "configured",
            "last_message": "用于自动采集失败时补充单篇文章正文或 HTML。",
        },
    }
    config = IntegrationConfig(id=new_id("int"), provider=provider, **defaults.get(provider, {}))
    session.add(config)
    session.flush()
    return config


def list_integrations(session: Session) -> list[IntegrationConfigRead]:
    providers = ["wechat-article-exporter", "wewe-rss", "supplement-import"]
    configs = [get_or_create_integration(session, provider) for provider in providers]
    session.commit()
    return [integration_to_schema(config) for config in configs]


def save_wewe_rss_config(session: Session, payload: WeweRssConfigRequest) -> IntegrationConfigRead:
    config = get_or_create_integration(session, "wewe-rss")
    config.base_url = payload.base_url.strip()
    config.feed_url = payload.feed_url.strip()
    config.auth_code = payload.auth_code.strip()
    config.status = "configured" if config.feed_url else "not_configured"
    config.last_message = "已保存 wewe-rss 配置。" if config.feed_url else "尚未填写 Feed 地址。"
    session.commit()
    return integration_to_schema(config)


def integration_to_schema(config: IntegrationConfig) -> IntegrationConfigRead:
    return IntegrationConfigRead(
        provider=config.provider,
        base_url=config.base_url,
        feed_url=config.feed_url,
        status=config.status,
        last_message=config.last_message,
        last_synced_at=config.last_synced_at,
    )
