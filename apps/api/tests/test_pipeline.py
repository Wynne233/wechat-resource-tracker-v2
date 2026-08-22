from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.extractors import _valid_resource_name, extract_resources
from app.models import Base, Resource, SourceAccount
from app.repository import (
    analyze_article_url,
    check_source_now,
    create_subscription,
    fetch_missing_fulltext_with_exporter,
    get_or_create_integration,
    import_history_json,
    import_supplement,
    import_wechat_exporter,
    list_notifications,
    save_wewe_rss_config,
    search_resources,
    sync_wewe_rss,
    run_due_source_checks,
)
from app.adapters import parse_wechat_exporter_content
from app.schemas import ArticleAnalyzeRequest, HistoryImportRequest, HistoryImportResponse, StandardArticle, SubscriptionCreate
from app.schemas import AdapterImportRequest, SupplementImportRequest, WeweRssConfigRequest, WeweRssSyncRequest


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_weekly_check_runs_one_feed_sync_for_all_due_sources(monkeypatch):
    session = make_session()
    payload = sample_payload()
    import_history_json(session, payload)
    source = session.query(SourceAccount).first()
    source.tracking_status = "active"
    source.next_check_at = datetime(2020, 1, 1)
    session.commit()

    called = {"sync": 0, "fulltext": 0}

    def fake_sync(_session, _payload):
        called["sync"] += 1
        return HistoryImportResponse(
            requested_count=3,
            imported_count=2,
            skipped_count=1,
            resource_count=1,
            results=[],
        )

    def fake_fulltext(_session, base_url="", limit=30):
        called["fulltext"] += 1
        assert limit == 2
        return HistoryImportResponse(
            requested_count=2,
            imported_count=2,
            skipped_count=0,
            resource_count=1,
            results=[],
        )

    monkeypatch.setattr("app.repository.sync_wewe_rss", fake_sync)
    monkeypatch.setattr("app.repository.fetch_missing_fulltext_with_exporter", fake_fulltext)

    result = run_due_source_checks(session)

    assert result.imported_count == 2
    assert called == {"sync": 1, "fulltext": 1}
    assert source.last_check_status == "success"
    assert source.next_check_at and source.next_check_at > datetime.now()


def sample_payload() -> HistoryImportRequest:
    return HistoryImportRequest(
        articles=[
            StandardArticle(
                source_name="效率工具研究所",
                source_identifier="efficiency-lab",
                title="AI 工具合集",
                article_url="https://mp.weixin.qq.com/s/test-ai",
                published_at=datetime(2026, 5, 8, 9, 30),
                content_text="Notion AI 是一个 AI 工具，适合整理知识库，官网 https://www.notion.so/product/ai。",
                read_count=None,
                like_count=None,
                comment_count=None,
                crawl_source="history_export",
            )
        ]
    )


def test_history_import_generates_resource_and_score():
    session = make_session()

    result = import_history_json(session, sample_payload())
    resources = session.query(Resource).all()

    assert result.imported_count == 1
    assert len(resources) == 1
    assert resources[0].latest_score > 0
    assert resources[0].latest_grade in {"S", "A", "B", "C"}


def test_duplicate_article_is_skipped():
    session = make_session()

    import_history_json(session, sample_payload())
    result = import_history_json(session, sample_payload())

    assert result.imported_count == 0
    assert result.skipped_count == 1


def test_search_finds_imported_resource():
    session = make_session()
    import_history_json(session, sample_payload())

    result = search_resources(session, "AI")

    assert result.total >= 1
    assert "Notion AI" in result.items[0].canonical_name


def test_title_only_article_does_not_generate_resource():
    session = make_session()
    payload = HistoryImportRequest(
        articles=[
            StandardArticle(
                source_name="标题列表",
                title="超好用音乐播放下载神器-青听音乐",
                article_url="https://mp.weixin.qq.com/s/title-only",
                content_text="",
            )
        ]
    )

    result = import_history_json(session, payload)

    assert result.imported_count == 1
    assert result.resource_count == 0
    assert session.query(Resource).count() == 0
    assert search_resources(session, "青听音乐").total == 0


def test_wechat_exporter_maps_account_name_fields():
    articles = parse_wechat_exporter_content(
        '[{"_accountName":"阿鱼小站","_biz":"MzDemo","articleTitle":"测试文章","contentUrl":"https://mp.weixin.qq.com/s/demo","content":"正文内容"}]'
    )

    assert articles[0].source_name == "阿鱼小站"
    assert articles[0].source_identifier == "MzDemo"
    assert articles[0].title == "测试文章"
    assert articles[0].article_url == "https://mp.weixin.qq.com/s/demo"


def test_exporter_fulltext_fetch_updates_title_only_article(monkeypatch):
    session = make_session()
    payload = HistoryImportRequest(
        articles=[
            StandardArticle(
                source_name="阿鱼小站",
                title="超好用音乐播放下载神器-青听音乐",
                article_url="https://mp.weixin.qq.com/s/qingting",
                content_text="",
            )
        ]
    )
    import_history_json(session, payload)

    monkeypatch.setattr(
        "app.repository.fetch_text_from_exporter",
        lambda article_url, base_url="http://127.0.0.1:4100": (
            "【软件名称】青听音乐 【适用设备】安卓。青听音乐是一款仅需导入音源即可免费搜索播放下载歌曲的 app，"
            "内含热门歌曲歌单，还可从其它主流音乐软件导入歌单。下载地址 https://pan.example.com/qingting"
        ),
    )

    result = fetch_missing_fulltext_with_exporter(session)

    assert result.imported_count == 1
    assert result.resource_count == 1
    assert search_resources(session, "青听音乐").total == 1


def test_subscription_generates_notification_on_matching_import():
    session = make_session()
    create_subscription(session, SubscriptionCreate(target_type="topic", target_value="AI", display_name="AI 工具"))

    import_history_json(session, sample_payload())
    notifications = list_notifications(session)

    assert len(notifications) == 1
    assert notifications[0].event_type == "resource_matched"


def test_wechat_exporter_import_accepts_export_json():
    session = make_session()
    payload = AdapterImportRequest(
        source_name="工具收藏夹",
        content="""
        [
          {
            "title": "剪辑工具推荐",
            "article_url": "https://mp.weixin.qq.com/s/exporter-demo",
            "published_at": "2026-05-01 10:00:00",
            "content_text": "CapCut 是一个剪辑工具，官网 https://www.capcut.com。"
          }
        ]
        """,
    )

    result = import_wechat_exporter(session, payload)

    assert result.imported_count == 1
    assert result.resource_count == 1
    assert search_resources(session, "CapCut").total == 1


def test_supplement_import_uses_same_pipeline():
    session = make_session()
    payload = SupplementImportRequest(
        source_name="手工补充",
        article_url="https://mp.weixin.qq.com/s/manual-demo",
        title="设计工具补充",
        content="Figma 是一个 Web 设计工具，官网 https://www.figma.com。",
    )

    result = import_supplement(session, payload)

    assert result.imported_count == 1
    assert search_resources(session, "Figma").total == 1


def test_wewe_rss_sync_uses_configured_feed(monkeypatch):
    session = make_session()
    save_wewe_rss_config(session, WeweRssConfigRequest(feed_url="http://127.0.0.1/feed.json"))

    def fake_fetch(feed_url, auth_code=None):
        assert feed_url == "http://127.0.0.1/feed.json"
        return [
            StandardArticle(
                source_name="增量公众号",
                title="同步工具推荐",
                article_url="https://mp.weixin.qq.com/s/rss-demo",
                content_text="Readwise Reader 是一个阅读工具，官网 https://readwise.io/read。",
                crawl_source="rss_sync",
            )
        ]

    monkeypatch.setattr("app.repository.fetch_wewe_rss_articles", fake_fetch)

    result = sync_wewe_rss(session, WeweRssSyncRequest())

    assert result.imported_count == 1
    assert search_resources(session, "Readwise").total == 1


def test_wewe_rss_sync_only_imports_unseen_articles_and_does_not_renotify(monkeypatch):
    session = make_session()
    save_wewe_rss_config(session, WeweRssConfigRequest(feed_url="http://127.0.0.1/feed.json"))
    create_subscription(session, SubscriptionCreate(target_type="topic", target_value="阅读", display_name="阅读工具"))

    feed_articles = [
        StandardArticle(
            source_name="增量公众号",
            title="阅读工具推荐",
            article_url="https://mp.weixin.qq.com/s/rss-incremental-demo",
            content_text="Readwise Reader 是一个阅读工具，官网 https://readwise.io/read。",
            crawl_source="rss_sync",
        )
    ]

    monkeypatch.setattr("app.repository.fetch_wewe_rss_articles", lambda feed_url, auth_code=None: feed_articles)

    first = sync_wewe_rss(session, WeweRssSyncRequest())
    second = sync_wewe_rss(session, WeweRssSyncRequest())
    notifications = list_notifications(session)

    assert first.requested_count == 1
    assert first.imported_count == 1
    assert first.skipped_count == 0
    assert second.requested_count == 1
    assert second.imported_count == 0
    assert second.skipped_count == 1
    assert len(notifications) == 1


def test_wewe_rss_sync_falls_back_to_stable_fulltext_url(monkeypatch):
    session = make_session()
    save_wewe_rss_config(session, WeweRssConfigRequest(feed_url="http://wewe.example.test/feeds/all.json"))
    calls: list[str] = []

    def fake_fetch(feed_url, auth_code=None):
        calls.append(feed_url)
        if feed_url == "http://wewe.example.test/feeds/all.json?mode=fulltext&limit=10":
            raise RuntimeError("502 Bad Gateway")
        assert feed_url == "http://wewe.example.test/feeds/all.json?mode=fulltext&limit=5"
        return [
            StandardArticle(
                source_name="增量公众号",
                title="小批量全文同步",
                article_url="https://mp.weixin.qq.com/s/rss-fallback-demo",
                content_text="ReaderX 是一个阅读工具，官网 https://reader.example.com。",
                crawl_source="rss_sync",
            )
        ]

    monkeypatch.setattr("app.repository.fetch_wewe_rss_articles", fake_fetch)

    result = sync_wewe_rss(session, WeweRssSyncRequest())
    config = get_or_create_integration(session, "wewe-rss")

    assert result.imported_count == 1
    assert calls == [
        "http://wewe.example.test/feeds/all.json?mode=fulltext&limit=10",
        "http://wewe.example.test/feeds/all.json?mode=fulltext&limit=5",
    ]
    assert config.feed_url == "http://wewe.example.test/feeds/all.json?mode=fulltext&limit=5"


def test_wewe_rss_sync_uses_local_sqlite_when_http_feed_fails(monkeypatch):
    session = make_session()
    save_wewe_rss_config(session, WeweRssConfigRequest(feed_url="http://127.0.0.1:4000/feeds/all.json"))

    monkeypatch.setattr("app.repository.fetch_wewe_rss_articles", lambda feed_url, auth_code=None: (_ for _ in ()).throw(RuntimeError("502 Bad Gateway")))
    monkeypatch.setattr(
        "app.repository.fetch_wewe_rss_local_articles",
        lambda: [
            StandardArticle(
                source_name="本地公众号",
                title="本地库文章",
                article_url="https://mp.weixin.qq.com/s/local-sqlite-demo",
                content_text="",
                crawl_source="wewe_rss_sqlite",
            )
        ],
    )

    result = sync_wewe_rss(session, WeweRssSyncRequest())
    config = get_or_create_integration(session, "wewe-rss")

    assert result.requested_count == 1
    assert result.imported_count == 1
    assert config.feed_url == "http://127.0.0.1:4000/feeds/all.json"
    assert "本地 wewe-rss 数据库" in config.last_message


def test_local_wewe_rss_sync_reads_all_known_articles(monkeypatch):
    session = make_session()
    save_wewe_rss_config(session, WeweRssConfigRequest(feed_url="http://127.0.0.1:4000/feeds/all.json"))

    monkeypatch.setattr(
        "app.repository.fetch_wewe_rss_local_articles",
        lambda: [
            StandardArticle(
                source_name="本地公众号",
                title=f"本地库文章 {index}",
                article_url=f"https://mp.weixin.qq.com/s/local-all-{index}",
                content_text="",
                crawl_source="wewe_rss_sqlite",
            )
            for index in range(35)
        ],
    )

    result = sync_wewe_rss(session, WeweRssSyncRequest())

    assert result.requested_count == 35
    assert result.imported_count == 35


def test_title_only_extraction_waits_for_full_text():
    titles = [
        "音乐下载神器-敦伦调调",
        "MusicFree 最新版，更新可用音源",
        "洛雪音乐助手最新版，附可用音源",
        "【Upscayl】让你的图片高清化",
        "Adobe 全家桶下载（2025 更新）",
    ]

    for title in titles:
        resources = extract_resources(
            StandardArticle(
                source_name="标题公众号",
                title=title,
                article_url=f"https://mp.weixin.qq.com/s/{title}",
                content_text="",
            )
        )
        assert resources == []


def test_badcase_bbplayer_is_searchable_by_capability_keyword():
    session = make_session()
    payload = HistoryImportRequest(
        articles=[
            StandardArticle(
                source_name="真实资源测试",
                title="BBPlayer 免费听歌 APP",
                article_url="https://mp.weixin.qq.com/s/wHFdu3AUWatU7bMNJ5nQQw",
                content_text=(
                    "BBPlayer 是一款听歌 APP，可以把 Bilibili 上感兴趣的音乐复制链接到这个 APP 免费听歌，"
                    "也支持音乐播放器和在线播放。官网 https://bbplayer.example.com"
                ),
                crawl_source="badcase",
            )
        ]
    )

    import_history_json(session, payload)
    result = search_resources(session, "免费听歌")

    assert result.total == 1
    assert result.items[0].canonical_name == "BBPlayer"
    assert "免费听歌" in result.items[0].capability_tags


def test_badcase_dunlun_diaodiao_does_not_create_generic_listening_resource():
    resources = extract_resources(
        StandardArticle(
            source_name="真实资源测试",
            title="敦伦调调 免费 APP 更新",
            article_url="https://mp.weixin.qq.com/s/dunlun-demo",
            content_text="敦伦调调是一款免费 APP，主打音乐播放和听歌体验，适合日常使用。",
            crawl_source="badcase",
        )
    )

    names = {item.name for item in resources}
    assert "敦伦调调" in names
    assert "听歌" not in names


def test_search_free_listening_prefers_music_resource_not_generic_free_resource():
    session = make_session()
    import_history_json(
        session,
        HistoryImportRequest(
            articles=[
                StandardArticle(
                    source_name="真实资源测试",
                    title="开源记账软件",
                    article_url="https://mp.weixin.qq.com/s/accounting-demo",
                    content_text="蜜蜂记账是一款开源免费的个人记账软件，支持 AI 记账和数据报表。",
                    crawl_source="badcase",
                ),
                StandardArticle(
                    source_name="真实资源测试",
                    title="音乐下载神器",
                    article_url="https://mp.weixin.qq.com/s/music-demo",
                    content_text="敦伦调调是一款安卓音乐下载神器，支持歌词下载、封面下载和无损音乐。",
                    crawl_source="badcase",
                ),
            ]
        ),
    )

    result = search_resources(session, "免费听歌")

    assert result.total >= 1
    assert result.items[0].canonical_name == "敦伦调调"
    assert all(item.canonical_name != "蜜蜂记账" for item in result.items)


def test_invalid_sentence_like_resource_names_are_rejected():
    invalid_names = [
        "大家好",
        "今天给大家带来一款好用的漫画软件",
        "两款开源软件",
        "仅支持安卓平台",
        "不过软件含有开屏广告",
        "Part.11",
        "一只喵倒下了",
    ]
    valid_names = ["囧次元", "动漫共和国", "蜜蜂记账", "AGE动漫", "敦伦调调"]

    assert all(not _valid_resource_name(name) for name in invalid_names)
    assert not _valid_resource_name(
        "阿鱼小站",
        evidence="三、软件下载关注下方微信公众号【阿鱼小站】聊天框发送数字〖206〗或者〖漫画〗",
    )
    assert all(_valid_resource_name(name) for name in valid_names)


def test_title_only_music_titles_do_not_create_weak_resources():
    titles = [
        "电脑也能用酷狗概念版免费听歌",
        "超好用音乐播放下载神器-青听音乐",
        "Alger新版音乐播放器",
        "又一款免费的B站音乐播放器",
    ]

    for title in titles:
        resources = extract_resources(
            StandardArticle(
                source_name="标题边界测试",
                title=title,
                article_url=f"https://mp.weixin.qq.com/s/{title}",
                content_text="",
            )
        )
        assert resources == []


def test_article_url_analysis_imports_fulltext_and_tracks_source(monkeypatch):
    session = make_session()
    monkeypatch.setattr(
        "app.repository.fetch_article_from_exporter",
        lambda article_url, base_url="http://127.0.0.1:4100": StandardArticle(
            source_name="阿鱼小站",
            source_identifier="MzDemo",
            title="BBPlayer 免费听歌 APP",
            article_url=article_url,
            content_text=(
                "BBPlayer 是一款听歌 APP，可以把 Bilibili 上感兴趣的音乐复制链接到这个 APP 免费听歌，"
                "也支持音乐播放器和在线播放。它适合想把视频平台音乐整理成播放列表的用户，"
                "文章提供了使用说明、导入方式和下载入口。官网 https://bbplayer.example.com"
            ),
            crawl_source="article_url_analysis",
        ),
    )

    result = analyze_article_url(session, ArticleAnalyzeRequest(article_url="https://mp.weixin.qq.com/s/analyze-demo"))

    assert result.content_status == "full_text"
    assert result.extraction_status == "success"
    assert result.tracking_status == "active"
    assert result.source_name == "阿鱼小站"
    assert result.created_resources == 1
    assert search_resources(session, "免费听歌").total == 1


def test_article_url_analysis_duplicate_does_not_duplicate_resources(monkeypatch):
    session = make_session()
    article = StandardArticle(
        source_name="阿鱼小站",
        title="BBPlayer 免费听歌 APP",
        article_url="https://mp.weixin.qq.com/s/analyze-duplicate",
        content_text="BBPlayer 是一款音乐播放器，支持免费听歌。官网 https://bbplayer.example.com",
        crawl_source="article_url_analysis",
    )
    monkeypatch.setattr("app.repository.fetch_article_from_exporter", lambda article_url, base_url="http://127.0.0.1:4100": article)

    first = analyze_article_url(session, ArticleAnalyzeRequest(article_url=article.article_url))
    second = analyze_article_url(session, ArticleAnalyzeRequest(article_url=article.article_url))

    assert first.created_resources == 1
    assert second.created_resources == 0
    assert session.query(Resource).count() == 1


def test_source_manual_check_has_cooldown(monkeypatch):
    session = make_session()
    source = import_history_json(session, sample_payload())
    source_id = session.query(Resource).first().mentions[0].article.source_id

    monkeypatch.setattr(
        "app.repository.sync_wewe_rss",
        lambda session, payload: import_history_json(
            session,
            HistoryImportRequest(
                articles=[
                    StandardArticle(
                        source_name="增量公众号",
                        title="新文章",
                        article_url="https://mp.weixin.qq.com/s/check-now-demo",
                        content_text="Readwise Reader 是一个阅读工具，官网 https://readwise.io/read。",
                    )
                ]
            ),
        ),
    )

    first = check_source_now(session, source_id)
    second = check_source_now(session, source_id)

    assert first.status == "success"
    assert second.status == "cooldown"
