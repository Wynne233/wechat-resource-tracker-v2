import type {
  AdminOverview,
  AdminResourceListResponse,
  FeishuSetting,
  IntegrationConfig,
  NotificationItem,
  ResourceDetail,
  SearchResource,
  SearchResponse,
  SourceAccount,
  Subscription,
  TaskLog,
} from "./api";

const resources: SearchResource[] = [
  {
    id: "demo-kazumi",
    canonical_name: "Kazumi",
    resource_type: "app",
    capability_tags: ["anime streaming", "Bangumi integration"],
    summary: "An anime streaming app with rule-based content retrieval and Bangumi integration.",
    current_status: "suspected_update",
    risk_level: "low",
    latest_score: 57.5,
    latest_grade: "C",
    source_count: 1,
    mention_count: 2,
    last_mentioned_at: "2026-08-23T05:33:39.624Z",
    explanation: "公众号文章提到新版本与规则更新，已记录为待复核的资源状态变化。",
    match_reason: "",
  },
  {
    id: "demo-bbplayer",
    canonical_name: "BBPlayer",
    resource_type: "app",
    capability_tags: ["music player", "Bilibili music"],
    summary: "A free music player for Bilibili music.",
    current_status: "suspected_update",
    risk_level: "low",
    latest_score: 57.5,
    latest_grade: "C",
    source_count: 1,
    mention_count: 2,
    last_mentioned_at: "2026-08-23T05:33:39.627Z",
    explanation: "从公众号更新文章中提取到功能与可用性变化线索。",
    match_reason: "",
  },
  {
    id: "demo-notion-ai",
    canonical_name: "Notion AI",
    resource_type: "tool",
    capability_tags: ["AI productivity", "knowledge management"],
    summary: "A tool for organizing meeting notes, project documents, and knowledge bases.",
    current_status: "available",
    risk_level: "low",
    latest_score: 58,
    latest_grade: "C",
    source_count: 1,
    mention_count: 1,
    last_mentioned_at: "2026-05-08T09:30:00Z",
    explanation: "来自已归档公众号文章的结构化资源条目。",
    match_reason: "",
  },
];

const sources: SourceAccount[] = [
  {
    id: "demo-source-enjoy",
    name: "享乐乎",
    source_type: "wechat",
    trust_level: "pending",
    trust_weight: 0.6,
    crawl_status: "normal",
    tracking_status: "active",
    tracking_source: "article_url_analysis",
    first_tracked_at: "2026-08-23T05:33:39Z",
    last_analyzed_at: "2026-08-23T05:42:22Z",
    last_checked_at: "2026-08-23T05:45:08Z",
    next_check_at: "2026-08-30T05:33:39Z",
    last_check_status: "success",
    last_check_message: "演示数据：已发现并归档 6 篇文章。",
    consecutive_failures: 0,
    notes: "",
    article_count: 6,
    resource_count: 3,
  },
];

const detail = (resource: SearchResource): ResourceDetail => ({
  ...resource,
  aliases: [],
  platforms: ["Web", "Desktop"],
  links: ["https://example.com"],
  risk_notes: resource.risk_level === "low" ? "未发现明确高风险提示。" : "建议人工复核。",
  score: {
    total_score: resource.latest_score,
    grade: resource.latest_grade,
    multi_source_score: 10,
    source_trust_score: 12,
    interaction_score: 8,
    freshness_score: 11,
    availability_score: 10,
    evidence_score: 12,
    risk_penalty: 5,
    explanation: resource.explanation,
  },
  sources: [{
    source_name: "享乐乎",
    source_trust_level: "pending",
    article_title: "APP更新：Kazumi、BBPlayer、MoeKoeMusic",
    article_url: "https://mp.weixin.qq.com/s/demo",
    published_at: "2026-08-02T17:10:24Z",
    evidence_snippet: "文章提到资源版本与功能更新。",
    confidence: 0.86,
  }],
  timeline: [{
    checked_at: "2026-08-23T05:33:39Z",
    target_url: "https://mp.weixin.qq.com/s/demo",
    result_status: resource.current_status,
    change_summary: "从后续公众号文章发现资源更新线索。",
    suggestion: "建议人工复核最新可用性。",
  }],
});

export function getDemoResponse(path: string): unknown {
  const pathname = path.split("?")[0];
  if (pathname === "/search") {
    const query = new URLSearchParams(path.split("?")[1] || "").get("q") || "";
    const normalized = query.toLowerCase();
    const items = normalized
      ? resources.filter((item) => `${item.canonical_name} ${item.summary} ${item.capability_tags.join(" ")}`.toLowerCase().includes(normalized))
      : resources;
    return { query, total: items.length, items, message: `演示资源库命中 ${items.length} 条结果。` } satisfies SearchResponse;
  }
  if (pathname.startsWith("/resources/")) return detail(resources.find((item) => item.id === pathname.split("/").pop()) || resources[0]);
  if (pathname === "/admin/resources") return { total: resources.length, items: resources } satisfies AdminResourceListResponse;
  if (pathname === "/admin/sources") return sources;
  if (pathname === "/admin/overview") {
    return {
      source_count: sources.length, article_count: 6, resource_count: resources.length, subscription_count: 2,
      notification_count: 2, pending_review_count: 2, latest_task_summary: "演示数据：文章解析与资源状态更新已完成。",
      database_path: "Vercel Demo", today_analyzed_count: 1, fulltext_success_count: 6,
      extraction_success_count: 6, tracked_source_count: 1, due_check_count: 0, ai_status: "demo",
    } satisfies AdminOverview;
  }
  if (pathname === "/subscriptions") return [{ id: "demo-subscription", target_type: "source", target_value: sources[0].id, display_name: "享乐乎", status: "active", created_at: "2026-08-23T05:33:39Z" }] satisfies Subscription[];
  if (pathname === "/notifications") return [{ id: "demo-notification", event_type: "resource_update", title: "BBPlayer 出现新版本线索", body: "后续公众号文章提到功能更新，等待人工复核。", resource_id: "demo-bbplayer", channel: "in_app", status: "sent", created_at: "2026-08-23T05:33:39Z" }] satisfies NotificationItem[];
  if (pathname === "/admin/integrations") return [{ provider: "wechat-article-exporter", base_url: "", feed_url: "", status: "demo", last_message: "演示版不运行采集服务。" }] satisfies IntegrationConfig[];
  if (pathname === "/admin/tasks") return [{ id: "demo-task", task_type: "article_url_analysis", status: "success", summary: "演示：已完成资源抽取与状态判断。", payload: {}, created_at: "2026-08-23T05:33:39Z" }] satisfies TaskLog[];
  if (pathname === "/notification-settings/feishu") return { status: "demo", masked_webhook: "演示版未配置", last_test_result: "不发送外部通知", last_tested_at: null } satisfies FeishuSetting;
  throw new Error(`演示版不支持该操作：${pathname}`);
}
