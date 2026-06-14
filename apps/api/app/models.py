from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SourceAccount(Base):
    __tablename__ = "source_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), default="wechat")
    trust_level: Mapped[str] = mapped_column(String(32), default="pending")
    trust_weight: Mapped[float] = mapped_column(Float, default=0.6)
    crawl_status: Mapped[str] = mapped_column(String(32), default="normal")
    tracking_status: Mapped[str] = mapped_column(String(32), default="paused", index=True)
    tracking_source: Mapped[str] = mapped_column(String(64), default="manual")
    first_tracked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_check_status: Mapped[str] = mapped_column(String(32), default="")
    last_check_message: Mapped[str] = mapped_column(Text, default="")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    articles: Mapped[list["Article"]] = relationship(back_populates="source")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_accounts.id"), index=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    article_url: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    content_text: Mapped[str] = mapped_column(Text)
    content_html: Mapped[str] = mapped_column(Text, default="")
    content_status: Mapped[str] = mapped_column(String(32), default="missing_content", index=True)
    extraction_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    extraction_version: Mapped[str] = mapped_column(String(32), default="")
    extraction_message: Mapped[str] = mapped_column(Text, default="")
    read_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crawl_source: Mapped[str] = mapped_column(String(64), default="history_export")
    crawl_status: Mapped[str] = mapped_column(String(32), default="success")
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    source: Mapped[SourceAccount] = relationship(back_populates="articles")
    mentions: Mapped[list["ResourceMention"]] = relationship(back_populates="article")


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(255), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    resource_type: Mapped[str] = mapped_column(String(64), default="tool")
    platforms: Mapped[list[str]] = mapped_column(JSON, default=list)
    capability_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    links: Mapped[list[str]] = mapped_column(JSON, default=list)
    current_status: Mapped[str] = mapped_column(String(32), default="available")
    risk_level: Mapped[str] = mapped_column(String(32), default="low")
    risk_notes: Mapped[str] = mapped_column(Text, default="")
    latest_score: Mapped[float] = mapped_column(Float, default=0.0)
    latest_grade: Mapped[str] = mapped_column(String(8), default="C")
    last_mentioned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    mentions: Mapped[list["ResourceMention"]] = relationship(back_populates="resource")
    scores: Mapped[list["ResourceScore"]] = relationship(back_populates="resource")
    status_checks: Mapped[list["StatusCheck"]] = relationship(back_populates="resource")


class ResourceMention(Base):
    __tablename__ = "resource_mentions"
    __table_args__ = (UniqueConstraint("resource_id", "article_id", "evidence_snippet"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.id"), index=True)
    evidence_snippet: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    extracted_name: Mapped[str] = mapped_column(String(255))
    match_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    resource: Mapped[Resource] = relationship(back_populates="mentions")
    article: Mapped[Article] = relationship(back_populates="mentions")


class ResourceScore(Base):
    __tablename__ = "resource_scores"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    total_score: Mapped[float] = mapped_column(Float)
    grade: Mapped[str] = mapped_column(String(8))
    multi_source_score: Mapped[float] = mapped_column(Float)
    source_trust_score: Mapped[float] = mapped_column(Float)
    interaction_score: Mapped[float] = mapped_column(Float)
    freshness_score: Mapped[float] = mapped_column(Float)
    availability_score: Mapped[float] = mapped_column(Float)
    evidence_score: Mapped[float] = mapped_column(Float)
    risk_penalty: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    resource: Mapped[Resource] = relationship(back_populates="scores")


class StatusCheck(Base):
    __tablename__ = "status_checks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"), index=True)
    target_url: Mapped[str] = mapped_column(String(1000), default="")
    result_status: Mapped[str] = mapped_column(String(32), default="available")
    change_summary: Mapped[str] = mapped_column(Text, default="首次入库，等待后续检测。")
    suggestion: Mapped[str] = mapped_column(Text, default="继续观察")
    check_source: Mapped[str] = mapped_column(String(64), default="initial_ingest")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    resource: Mapped[Resource] = relationship(back_populates="status_checks")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), default="default-user", index=True)
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    target_value: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), default="default-user", index=True)
    subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="in_app")
    status: Mapped[str] = mapped_column(String(32), default="unread")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationSetting(Base):
    __tablename__ = "notification_settings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), default="default-user", unique=True)
    feishu_webhook: Mapped[str] = mapped_column(Text, default="")
    feishu_status: Mapped[str] = mapped_column(String(32), default="not_configured")
    last_test_result: Mapped[str] = mapped_column(Text, default="")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ManualReview(Base):
    __tablename__ = "manual_reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    action_type: Mapped[str] = mapped_column(String(64))
    before_value: Mapped[dict] = mapped_column(JSON, default=dict)
    after_value: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskLog(Base):
    __tablename__ = "task_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="success")
    summary: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(1000), default="")
    feed_url: Mapped[str] = mapped_column(String(1000), default="")
    auth_code: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="not_configured")
    last_message: Mapped[str] = mapped_column(Text, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
