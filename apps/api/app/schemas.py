from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StandardArticle(BaseModel):
    source_name: str
    source_identifier: str | None = None
    title: str
    article_url: str
    published_at: datetime | None = None
    content_text: str
    content_html: str = ""
    read_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    crawl_source: str = "history_export"
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class HistoryImportRequest(BaseModel):
    articles: list[StandardArticle]


class AdapterImportRequest(BaseModel):
    content: str
    file_name: str = ""
    source_name: str = ""


class SupplementImportRequest(BaseModel):
    source_name: str
    article_url: str
    title: str = ""
    published_at: datetime | None = None
    content: str


class ImportResultItem(BaseModel):
    article_url: str
    status: str
    article_id: str | None = None
    imported_resources: list[str] = Field(default_factory=list)
    message: str = ""


class HistoryImportResponse(BaseModel):
    requested_count: int
    imported_count: int
    skipped_count: int
    resource_count: int
    results: list[ImportResultItem]


class ScoreBreakdown(BaseModel):
    total_score: float
    grade: str
    multi_source_score: float
    source_trust_score: float
    interaction_score: float
    freshness_score: float
    availability_score: float
    evidence_score: float
    risk_penalty: float
    explanation: str


class SearchResource(BaseModel):
    id: str
    canonical_name: str
    resource_type: str
    capability_tags: list[str] = Field(default_factory=list)
    summary: str
    current_status: str
    risk_level: str
    latest_score: float
    latest_grade: str
    source_count: int
    mention_count: int
    last_mentioned_at: datetime | None
    explanation: str
    match_reason: str = ""


class SearchResponse(BaseModel):
    query: str
    total: int
    items: list[SearchResource]
    message: str


class SourceEvidence(BaseModel):
    source_name: str
    source_trust_level: str
    article_title: str
    article_url: str
    published_at: datetime | None
    evidence_snippet: str
    confidence: float


class StatusTimelineItem(BaseModel):
    checked_at: datetime
    target_url: str
    result_status: str
    change_summary: str
    suggestion: str


class ResourceDetail(BaseModel):
    id: str
    canonical_name: str
    aliases: list[str]
    resource_type: str
    platforms: list[str]
    capability_tags: list[str]
    summary: str
    links: list[str]
    current_status: str
    risk_level: str
    risk_notes: str
    score: ScoreBreakdown
    sources: list[SourceEvidence]
    timeline: list[StatusTimelineItem]


class SubscriptionCreate(BaseModel):
    target_type: Literal["topic", "resource", "source"]
    target_value: str
    display_name: str | None = None


class SubscriptionRead(BaseModel):
    id: str
    target_type: str
    target_value: str
    display_name: str
    status: str
    created_at: datetime


class NotificationRead(BaseModel):
    id: str
    event_type: str
    title: str
    body: str
    resource_id: str | None
    channel: str
    status: str
    created_at: datetime


class FeishuSettingCreate(BaseModel):
    webhook_url: str


class FeishuSettingRead(BaseModel):
    status: str
    masked_webhook: str
    last_test_result: str
    last_tested_at: datetime | None


class SourceCreate(BaseModel):
    name: str
    source_identifier: str | None = None
    source_type: str = "wechat"
    trust_level: str = "pending"
    notes: str = ""


class SourceRead(BaseModel):
    id: str
    name: str
    source_identifier: str | None
    source_type: str
    trust_level: str
    trust_weight: float
    crawl_status: str
    tracking_status: str = "paused"
    tracking_source: str = "manual"
    first_tracked_at: datetime | None = None
    last_analyzed_at: datetime | None = None
    last_checked_at: datetime | None = None
    next_check_at: datetime | None = None
    last_check_status: str = ""
    last_check_message: str = ""
    consecutive_failures: int = 0
    notes: str
    article_count: int
    resource_count: int


class ManualReviewRequest(BaseModel):
    canonical_name: str | None = None
    summary: str | None = None
    current_status: str | None = None
    risk_level: str | None = None
    risk_notes: str | None = None
    links: list[str] | None = None
    note: str = ""


class ManualReviewResponse(BaseModel):
    resource_id: str
    review_id: str
    score: ScoreBreakdown


class AdminOverview(BaseModel):
    source_count: int
    article_count: int
    resource_count: int
    subscription_count: int
    notification_count: int
    pending_review_count: int
    latest_task_summary: str = ""
    database_path: str = ""
    today_analyzed_count: int = 0
    fulltext_success_count: int = 0
    extraction_success_count: int = 0
    tracked_source_count: int = 0
    due_check_count: int = 0
    ai_status: str = "unknown"


class TaskLogRead(BaseModel):
    id: str
    task_type: str
    status: str
    summary: str
    payload: dict[str, Any]
    created_at: datetime


class IntegrationConfigRead(BaseModel):
    provider: str
    base_url: str
    feed_url: str
    status: str
    last_message: str
    last_synced_at: datetime | None


class WeweRssConfigRequest(BaseModel):
    base_url: str = ""
    feed_url: str
    auth_code: str = ""


class WeweRssSyncRequest(BaseModel):
    feed_url: str = ""


class ArticleAnalyzeRequest(BaseModel):
    article_url: str
    exporter_base_url: str = "http://127.0.0.1:4100"


class AnalyzedResource(BaseModel):
    id: str
    canonical_name: str
    latest_score: float
    latest_grade: str
    current_status: str
    risk_level: str
    summary: str
    evidence_snippet: str = ""


class ArticleAnalyzeResponse(BaseModel):
    article_id: str | None = None
    source_id: str | None = None
    source_name: str = ""
    article_title: str = ""
    article_url: str
    content_status: str
    extraction_status: str
    tracking_status: str = "pending"
    created_resources: int = 0
    updated_resources: int = 0
    notifications_created: int = 0
    resources: list[AnalyzedResource] = Field(default_factory=list)
    message: str


class SourceTrackingRequest(BaseModel):
    tracking_status: Literal["active", "paused", "pending"]


class SourceCheckResponse(BaseModel):
    source_id: str
    status: str
    message: str
    result: HistoryImportResponse | None = None
