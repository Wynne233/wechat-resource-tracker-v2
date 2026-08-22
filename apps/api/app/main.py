from __future__ import annotations

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import ROOT, create_session, engine, ensure_runtime_schema, get_session
from .models import Article, Base, Resource
from .repository import (
    admin_overview,
    analyze_article_url,
    apply_manual_review,
    bulk_update_resources,
    check_source_now,
    create_source,
    create_subscription,
    delete_resource,
    delete_resources,
    fetch_missing_fulltext_with_exporter,
    get_feishu_setting,
    get_resource_detail,
    import_history_json,
    import_supplement,
    import_wechat_exporter,
    list_admin_resources,
    list_integrations,
    list_notifications,
    list_sources,
    list_subscriptions,
    list_task_logs,
    recalculate_score_by_id,
    reparse_all_articles,
    run_due_source_checks,
    save_wewe_rss_config,
    search_resources,
    sync_wewe_rss,
    test_feishu_setting,
    update_source_tracking,
    upsert_feishu_setting,
)
from .schemas import (
    AdapterImportRequest,
    AdminOverview,
    AdminResourceListResponse,
    ArticleAnalyzeRequest,
    ArticleAnalyzeResponse,
    FeishuSettingCreate,
    FeishuSettingRead,
    HistoryImportRequest,
    HistoryImportResponse,
    IntegrationConfigRead,
    ManualReviewRequest,
    ManualReviewResponse,
    NotificationRead,
    ResourceBulkActionResponse,
    ResourceBulkUpdateRequest,
    ResourceDetail,
    ScoreBreakdown,
    SearchResponse,
    SourceCheckResponse,
    SourceCreate,
    SourceRead,
    SourceTrackingRequest,
    SupplementImportRequest,
    SubscriptionCreate,
    SubscriptionRead,
    TaskLogRead,
    WeweRssConfigRequest,
    WeweRssSyncRequest,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    reset_corrupt_demo_data_if_requested()
    seed_demo_data_if_empty()
    yield


def reset_corrupt_demo_data_if_requested() -> None:
    if os.getenv("RESOURCE_TRACKER_RESET_CORRUPT_DEMO_DATA", "").lower() not in {"1", "true", "yes"}:
        return
    with create_session() as session:
        names = [name or "" for (name,) in session.query(Resource.canonical_name).limit(50).all()]
        if names and not any("�" in name or "锟" in name for name in names):
            return
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()


def seed_demo_data_if_empty() -> None:
    seed_file = Path(ROOT) / "sample_data" / "articles.json"
    if not seed_file.exists():
        return
    with create_session() as session:
        if session.query(Article).count() > 0:
            return
        payload = HistoryImportRequest(articles=json.loads(seed_file.read_text(encoding="utf-8")))
        import_history_json(session, payload)


def reset_demo_data() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    seed_demo_data_if_empty()


app = FastAPI(title="公众号资源发现与追踪助手 V2 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/internal/jobs/weekly-source-check", response_model=HistoryImportResponse)
def internal_weekly_source_check(
    x_scheduler_token: str = Header(default=""),
    session: Session = Depends(get_session),
) -> HistoryImportResponse:
    expected_token = os.getenv("SCHEDULER_TOKEN", "").strip()
    if not expected_token:
        raise HTTPException(status_code=503, detail="Scheduled checks are not configured.")
    if x_scheduler_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid scheduler token.")
    try:
        return run_due_source_checks(session)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Weekly source check failed: {exc}") from exc


@app.get("/search", response_model=SearchResponse)
def search(q: str = Query(default=""), session: Session = Depends(get_session)) -> SearchResponse:
    return search_resources(session, q)


@app.get("/resources/{resource_id}", response_model=ResourceDetail)
def resource_detail(resource_id: str, session: Session = Depends(get_session)) -> ResourceDetail:
    detail = get_resource_detail(session, resource_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="资源不存在")
    return detail


@app.post("/articles/analyze-url", response_model=ArticleAnalyzeResponse)
def article_analyze_url(payload: ArticleAnalyzeRequest, session: Session = Depends(get_session)) -> ArticleAnalyzeResponse:
    try:
        return analyze_article_url(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/subscriptions", response_model=SubscriptionRead, status_code=201)
def subscriptions_create(payload: SubscriptionCreate, session: Session = Depends(get_session)) -> SubscriptionRead:
    return create_subscription(session, payload)


@app.get("/subscriptions", response_model=list[SubscriptionRead])
def subscriptions(session: Session = Depends(get_session)) -> list[SubscriptionRead]:
    return list_subscriptions(session)


@app.get("/notifications", response_model=list[NotificationRead])
def notifications(session: Session = Depends(get_session)) -> list[NotificationRead]:
    return list_notifications(session)


@app.get("/notification-settings/feishu", response_model=FeishuSettingRead)
def feishu_setting(session: Session = Depends(get_session)) -> FeishuSettingRead:
    return get_feishu_setting(session)


@app.post("/notification-settings/feishu", response_model=FeishuSettingRead)
def feishu_setting_save(payload: FeishuSettingCreate, session: Session = Depends(get_session)) -> FeishuSettingRead:
    return upsert_feishu_setting(session, payload.webhook_url)


@app.post("/notification-settings/feishu/test", response_model=FeishuSettingRead)
def feishu_setting_test(payload: FeishuSettingCreate, session: Session = Depends(get_session)) -> FeishuSettingRead:
    return test_feishu_setting(session, payload.webhook_url)


@app.get("/admin/overview", response_model=AdminOverview)
def admin_dashboard(session: Session = Depends(get_session)) -> AdminOverview:
    return admin_overview(session)


@app.get("/admin/sources", response_model=list[SourceRead])
def admin_sources(session: Session = Depends(get_session)) -> list[SourceRead]:
    return list_sources(session)


@app.get("/admin/resources", response_model=AdminResourceListResponse)
def admin_resources(
    q: str = Query(default=""),
    status: str = Query(default=""),
    risk: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> AdminResourceListResponse:
    return list_admin_resources(session, q=q, status=status, risk=risk, page=page, page_size=page_size)


@app.delete("/admin/resources/{resource_id}", response_model=ResourceBulkActionResponse)
def admin_resource_delete(resource_id: str, session: Session = Depends(get_session)) -> ResourceBulkActionResponse:
    return delete_resource(session, resource_id)


@app.post("/admin/resources/bulk-delete", response_model=ResourceBulkActionResponse)
def admin_resources_bulk_delete(payload: ResourceBulkUpdateRequest, session: Session = Depends(get_session)) -> ResourceBulkActionResponse:
    return delete_resources(session, payload.resource_ids)


@app.post("/admin/resources/bulk-update", response_model=ResourceBulkActionResponse)
def admin_resources_bulk_update(payload: ResourceBulkUpdateRequest, session: Session = Depends(get_session)) -> ResourceBulkActionResponse:
    return bulk_update_resources(session, payload)


@app.post("/admin/sources", response_model=SourceRead, status_code=201)
def admin_sources_create(payload: SourceCreate, session: Session = Depends(get_session)) -> SourceRead:
    return create_source(session, payload)


@app.post("/admin/sources/{source_id}/tracking", response_model=SourceRead)
def admin_source_tracking(source_id: str, payload: SourceTrackingRequest, session: Session = Depends(get_session)) -> SourceRead:
    try:
        return update_source_tracking(session, source_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/admin/sources/{source_id}/check-now", response_model=SourceCheckResponse)
def admin_source_check_now(source_id: str, session: Session = Depends(get_session)) -> SourceCheckResponse:
    try:
        return check_source_now(session, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/admin/imports/history-json", response_model=HistoryImportResponse, status_code=201)
def admin_import_history_json(payload: HistoryImportRequest, session: Session = Depends(get_session)) -> HistoryImportResponse:
    return import_history_json(session, payload)


@app.post("/admin/imports/wechat-exporter", response_model=HistoryImportResponse, status_code=201)
def admin_import_wechat_exporter(payload: AdapterImportRequest, session: Session = Depends(get_session)) -> HistoryImportResponse:
    return import_wechat_exporter(session, payload)


@app.post("/admin/imports/supplement", response_model=HistoryImportResponse, status_code=201)
def admin_import_supplement(payload: SupplementImportRequest, session: Session = Depends(get_session)) -> HistoryImportResponse:
    return import_supplement(session, payload)


@app.post("/admin/articles/fetch-fulltext", response_model=HistoryImportResponse)
def admin_fetch_fulltext(
    base_url: str = Query(default="http://127.0.0.1:4100"),
    limit: int = Query(default=30, ge=1, le=100),
    session: Session = Depends(get_session),
) -> HistoryImportResponse:
    return fetch_missing_fulltext_with_exporter(session, base_url=base_url, limit=limit)


@app.get("/admin/integrations", response_model=list[IntegrationConfigRead])
def admin_integrations(session: Session = Depends(get_session)) -> list[IntegrationConfigRead]:
    return list_integrations(session)


@app.post("/admin/integrations/wewe-rss", response_model=IntegrationConfigRead)
def admin_wewe_rss_config(payload: WeweRssConfigRequest, session: Session = Depends(get_session)) -> IntegrationConfigRead:
    return save_wewe_rss_config(session, payload)


@app.post("/admin/sync/wewe-rss", response_model=HistoryImportResponse)
def admin_wewe_rss_sync(payload: WeweRssSyncRequest, session: Session = Depends(get_session)) -> HistoryImportResponse:
    try:
        return sync_wewe_rss(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/admin/tasks", response_model=list[TaskLogRead])
def admin_tasks(session: Session = Depends(get_session)) -> list[TaskLogRead]:
    return list_task_logs(session)


@app.post("/admin/demo/reset")
def admin_demo_reset(confirm: str = Query(default="")) -> dict[str, str]:
    if confirm != "reset-demo-data":
        raise HTTPException(status_code=400, detail="需要确认参数 confirm=reset-demo-data")
    reset_demo_data()
    return {"status": "ok", "message": "演示数据已重置"}


@app.post("/admin/resources/{resource_id}/review", response_model=ManualReviewResponse)
def admin_resource_review(
    resource_id: str,
    payload: ManualReviewRequest,
    session: Session = Depends(get_session),
) -> ManualReviewResponse:
    try:
        return apply_manual_review(session, resource_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/admin/resources/{resource_id}/recalculate-score", response_model=ScoreBreakdown)
def admin_resource_recalculate(resource_id: str, session: Session = Depends(get_session)) -> ScoreBreakdown:
    try:
        return recalculate_score_by_id(session, resource_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/admin/extraction/reparse-all", response_model=HistoryImportResponse)
def admin_reparse_all(session: Session = Depends(get_session)) -> HistoryImportResponse:
    return reparse_all_articles(session)
