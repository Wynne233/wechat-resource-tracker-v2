export type SearchResource = {
  id: string;
  canonical_name: string;
  resource_type: string;
  capability_tags: string[];
  summary: string;
  current_status: string;
  risk_level: string;
  latest_score: number;
  latest_grade: string;
  source_count: number;
  mention_count: number;
  last_mentioned_at?: string | null;
  explanation: string;
  match_reason: string;
};

export type SearchResponse = {
  query: string;
  total: number;
  items: SearchResource[];
  message: string;
};

export type ResourceDetail = {
  id: string;
  canonical_name: string;
  aliases: string[];
  resource_type: string;
  platforms: string[];
  capability_tags: string[];
  summary: string;
  links: string[];
  current_status: string;
  risk_level: string;
  risk_notes: string;
  score: {
    total_score: number;
    grade: string;
    multi_source_score: number;
    source_trust_score: number;
    interaction_score: number;
    freshness_score: number;
    availability_score: number;
    evidence_score: number;
    risk_penalty: number;
    explanation: string;
  };
  sources: Array<{
    source_name: string;
    source_trust_level: string;
    article_title: string;
    article_url: string;
    published_at?: string | null;
    evidence_snippet: string;
    confidence: number;
  }>;
  timeline: Array<{
    checked_at: string;
    target_url: string;
    result_status: string;
    change_summary: string;
    suggestion: string;
  }>;
};

export type Subscription = {
  id: string;
  target_type: string;
  target_value: string;
  display_name: string;
  status: string;
  created_at: string;
};

export type NotificationItem = {
  id: string;
  event_type: string;
  title: string;
  body: string;
  resource_id?: string | null;
  channel: string;
  status: string;
  created_at: string;
};

export type SourceAccount = {
  id: string;
  name: string;
  source_identifier?: string | null;
  source_type: string;
  trust_level: string;
  trust_weight: number;
  crawl_status: string;
  tracking_status: string;
  tracking_source: string;
  first_tracked_at?: string | null;
  last_analyzed_at?: string | null;
  last_checked_at?: string | null;
  next_check_at?: string | null;
  last_check_status: string;
  last_check_message: string;
  consecutive_failures: number;
  notes: string;
  article_count: number;
  resource_count: number;
};

export type AdminOverview = {
  source_count: number;
  article_count: number;
  resource_count: number;
  subscription_count: number;
  notification_count: number;
  pending_review_count: number;
  latest_task_summary: string;
  database_path: string;
  today_analyzed_count: number;
  fulltext_success_count: number;
  extraction_success_count: number;
  tracked_source_count: number;
  due_check_count: number;
  ai_status: string;
};

export type IntegrationConfig = {
  provider: string;
  base_url: string;
  feed_url: string;
  status: string;
  last_message: string;
  last_synced_at?: string | null;
};

export type TaskLog = {
  id: string;
  task_type: string;
  status: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type FeishuSetting = {
  status: string;
  masked_webhook: string;
  last_test_result: string;
  last_tested_at?: string | null;
};

export type ArticleAnalyzeResponse = {
  article_id?: string | null;
  source_id?: string | null;
  source_name: string;
  article_title: string;
  article_url: string;
  content_status: string;
  extraction_status: string;
  tracking_status: string;
  created_resources: number;
  updated_resources: number;
  notifications_created: number;
  message: string;
  resources: Array<{
    id: string;
    canonical_name: string;
    latest_score: number;
    latest_grade: string;
    current_status: string;
    risk_level: string;
    summary: string;
    evidence_snippet: string;
  }>;
};

export type SourceCheckResponse = {
  source_id: string;
  status: string;
  message: string;
};

const API_BASE = typeof window === "undefined"
  ? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001"
  : "/api/backend";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${path}`);
  }
  return response.json() as Promise<T>;
}

export function searchResources(query: string) {
  return fetchJson<SearchResponse>(`/search?q=${encodeURIComponent(query)}`);
}

export function analyzeArticleUrl(articleUrl: string) {
  return fetchJson<ArticleAnalyzeResponse>("/articles/analyze-url", {
    method: "POST",
    body: JSON.stringify({ article_url: articleUrl }),
  });
}

export function getResource(id: string) {
  return fetchJson<ResourceDetail>(`/resources/${id}`);
}

export function getSubscriptions() {
  return fetchJson<Subscription[]>("/subscriptions");
}

export function getNotifications() {
  return fetchJson<NotificationItem[]>("/notifications");
}

export function getSources() {
  return fetchJson<SourceAccount[]>("/admin/sources");
}

export function updateSourceTracking(sourceId: string, trackingStatus: string) {
  return fetchJson<SourceAccount>(`/admin/sources/${sourceId}/tracking`, {
    method: "POST",
    body: JSON.stringify({ tracking_status: trackingStatus }),
  });
}

export function checkSourceNow(sourceId: string) {
  return fetchJson<SourceCheckResponse>(`/admin/sources/${sourceId}/check-now`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getAdminOverview() {
  return fetchJson<AdminOverview>("/admin/overview");
}

export function getAdminResources() {
  return fetchJson<SearchResource[]>("/admin/resources");
}

export function getIntegrations() {
  return fetchJson<IntegrationConfig[]>("/admin/integrations");
}

export function getTaskLogs() {
  return fetchJson<TaskLog[]>("/admin/tasks");
}

export function reparseAllArticles() {
  return fetchJson<{ requested_count: number; imported_count: number; skipped_count: number; resource_count: number }>("/admin/extraction/reparse-all", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function fetchArticleFulltext(limit = 30) {
  return fetchJson<{ requested_count: number; imported_count: number; skipped_count: number; resource_count: number }>(
    `/admin/articles/fetch-fulltext?limit=${limit}`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}

export function getFeishuSetting() {
  return fetchJson<FeishuSetting>("/notification-settings/feishu");
}

export { API_BASE };
