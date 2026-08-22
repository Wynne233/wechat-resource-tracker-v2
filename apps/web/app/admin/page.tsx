import { ArticleUrlAnalyzeForm } from "@/components/article-url-analyze-form";
import { SupplementImportForm, WechatExporterImportForm, WeweRssSyncForm } from "@/components/collector-forms";
import { FulltextFetchButton } from "@/components/fulltext-fetch-button";
import { ReparseButton } from "@/components/reparse-button";
import { ResourceWorkbench } from "@/components/resource-workbench";
import { SourceActions } from "@/components/source-actions";
import { SourceForm } from "@/components/source-form";
import { getAdminOverview, getAdminResources, getIntegrations, getSources, getTaskLogs } from "@/lib/api";

export const dynamic = "force-dynamic";

function metricTone(label: string) {
  if (label.includes("待复核") || label.includes("失败")) return "warning";
  if (label.includes("AI")) return "info";
  return "";
}

export default async function AdminPage() {
  const [overview, sources, resourcePage, integrations, tasks] = await Promise.all([
    getAdminOverview(),
    getSources(),
    getAdminResources({ pageSize: 200 }),
    getIntegrations(),
    getTaskLogs(),
  ]);
  const weweRss = integrations.find((item) => item.provider === "wewe-rss");

  const metrics = [
    ["资源总数", overview.resource_count],
    ["待复核", overview.pending_review_count],
    ["文章", overview.article_count],
    ["来源", overview.source_count],
    ["订阅", overview.subscription_count],
    ["AI 状态", overview.ai_status],
  ];

  return (
    <>
      <section className="admin-hero">
        <div>
          <h1>资源情报工作台</h1>
          <p>
            这里先管理资源质量，再处理采集任务。资源是核心对象，文章和公众号只是证据来源。
          </p>
        </div>
        <div className="hero-actions">
          <a className="button ghost" href="/search?q=AI">查看搜索页</a>
          <a className="button" href="/settings">通知设置</a>
        </div>
      </section>

      <section className="metric-strip">
        {metrics.map(([label, value]) => (
          <div className={`ops-metric ${metricTone(String(label))}`} key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      <ResourceWorkbench resources={resourcePage.items} total={resourcePage.total} />

      <section className="admin-grid">
        <ArticleUrlAnalyzeForm compact />
        <div className="ops-panel">
          <h2>当前运行状态</h2>
          <div className="ops-list">
            <div><span>数据库</span><strong>{overview.database_path}</strong></div>
            <div><span>今日链接分析</span><strong>{overview.today_analyzed_count}</strong></div>
            <div><span>全文成功文章</span><strong>{overview.fulltext_success_count}</strong></div>
            <div><span>解析成功文章</span><strong>{overview.extraction_success_count}</strong></div>
            <div><span>追踪中来源</span><strong>{overview.tracked_source_count}</strong></div>
            <div><span>本周待检查</span><strong>{overview.due_check_count}</strong></div>
          </div>
          <p className="muted">最近任务：{overview.latest_task_summary || "暂无任务"}</p>
        </div>
      </section>

      <section className="admin-section">
        <div className="section-heading">
          <h2>来源追踪</h2>
          <p>公众号来源只负责提供证据，不再和资源管理混在一起。</p>
        </div>
        <div className="source-layout">
          <SourceForm />
          <div className="source-table-wrap">
            <table className="resource-table compact">
              <thead>
                <tr>
                  <th>公众号</th>
                  <th>追踪</th>
                  <th>文章/资源</th>
                  <th>最近检查</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => (
                  <tr key={source.id}>
                    <td>
                      <strong>{source.name}</strong>
                      <div className="muted">{source.trust_level} / {source.trust_weight}</div>
                    </td>
                    <td><span className={`status ${source.tracking_status}`}>{source.tracking_status}</span></td>
                    <td>{source.article_count} / {source.resource_count}</td>
                    <td>
                      {source.last_checked_at ? new Date(source.last_checked_at).toLocaleString("zh-CN") : "未检查"}
                      <div className="muted">{source.last_check_message || "暂无结果"}</div>
                    </td>
                    <td><SourceActions sourceId={source.id} trackingStatus={source.tracking_status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="admin-section">
        <div className="section-heading">
          <h2>采集与导入</h2>
          <p>这些是数据入口，不是日常管理主界面。真实公众号采集依赖 exporter / wewe-rss 的登录态。</p>
        </div>
        <div className="admin-grid">
          <WeweRssSyncForm integration={weweRss} />
          <div className="ops-panel actions-panel">
            <FulltextFetchButton />
            <ReparseButton />
          </div>
        </div>
        <div className="admin-grid">
          <WechatExporterImportForm />
          <SupplementImportForm />
        </div>
      </section>

      <section className="admin-section">
        <div className="section-heading">
          <h2>任务日志</h2>
          <p>只保留最近任务，帮助定位采集、解析、通知失败。</p>
        </div>
        <table className="resource-table compact">
          <thead>
            <tr>
              <th>时间</th>
              <th>任务</th>
              <th>状态</th>
              <th>摘要</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task) => (
              <tr key={task.id}>
                <td>{new Date(task.created_at).toLocaleString("zh-CN")}</td>
                <td>{task.task_type}</td>
                <td><span className={`status ${task.status}`}>{task.status}</span></td>
                <td>{task.summary}</td>
              </tr>
            ))}
            {!tasks.length ? (
              <tr>
                <td colSpan={4}><div className="empty-state">暂无任务日志</div></td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </>
  );
}
