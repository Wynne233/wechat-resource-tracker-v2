import { SupplementImportForm, WechatExporterImportForm, WeweRssSyncForm } from "@/components/collector-forms";
import { ArticleUrlAnalyzeForm } from "@/components/article-url-analyze-form";
import { FulltextFetchButton } from "@/components/fulltext-fetch-button";
import { ReparseButton } from "@/components/reparse-button";
import { ReviewForm } from "@/components/review-form";
import { SourceActions } from "@/components/source-actions";
import { SourceForm } from "@/components/source-form";
import { getAdminOverview, getAdminResources, getIntegrations, getSources, getTaskLogs } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const [overview, sources, resources, integrations, tasks] = await Promise.all([
    getAdminOverview(),
    getSources(),
    getAdminResources(),
    getIntegrations(),
    getTaskLogs(),
  ]);
  const weweRss = integrations.find((item) => item.provider === "wewe-rss");

  const metrics = [
    ["公众号", overview.source_count],
    ["文章", overview.article_count],
    ["资源", overview.resource_count],
    ["订阅", overview.subscription_count],
    ["通知", overview.notification_count],
    ["待复核", overview.pending_review_count],
  ];
  const trackerMetrics = [
    ["今日分析", overview.today_analyzed_count],
    ["全文成功", overview.fulltext_success_count],
    ["解析成功", overview.extraction_success_count],
    ["追踪中", overview.tracked_source_count],
    ["待检查", overview.due_check_count],
    ["AI 状态", overview.ai_status],
  ];

  return (
    <>
      <section className="section-header">
        <div>
          <span className="badge">管理后台</span>
          <h1 className="section-title">采集、入库、修正</h1>
          <p className="section-subtitle">按 PRD 第九章运行：历史冷启动、增量同步、补充导入全部先转成统一文章对象。</p>
        </div>
      </section>

      <section className="section grid three">
        {metrics.map(([label, value]) => (
          <div className="metric" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      <section className="section card">
        <div className="card-heading">
          <h2>真实数据状态</h2>
          <span className="badge">SQLite 文件库</span>
        </div>
        <div className="meta">
          <span>数据库：{overview.database_path}</span>
          <span>最近任务：{overview.latest_task_summary || "暂无任务"}</span>
        </div>
      </section>

      <section className="section grid three">
        {trackerMetrics.map(([label, value]) => (
          <div className="metric" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      <section className="section">
        <ArticleUrlAnalyzeForm compact />
      </section>

      <section className="section grid two">
        <SourceForm />
        <WeweRssSyncForm integration={weweRss} />
      </section>

      <section className="section">
        <WechatExporterImportForm />
      </section>

      <section className="section">
        <SupplementImportForm />
      </section>

      <section className="section grid two">
        <FulltextFetchButton />
        <ReparseButton />
      </section>

      <section className="section card">
        <h2>公众号来源池</h2>
        <table className="table">
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>可信度</th>
              <th>采集状态</th>
              <th>追踪</th>
              <th>文章/资源</th>
              <th>备注</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr key={source.id}>
                <td>{source.name}</td>
                <td>{source.source_type}</td>
                <td>{source.trust_level} / {source.trust_weight}</td>
                <td>{source.crawl_status}</td>
                <td>
                  <span className={`status ${source.tracking_status}`}>{source.tracking_status}</span>
                  <div className="muted">下次：{source.next_check_at ? new Date(source.next_check_at).toLocaleDateString("zh-CN") : "未排程"}</div>
                  <div className="muted">{source.last_check_message || "暂无检查记录"}</div>
                </td>
                <td>{source.article_count} / {source.resource_count}</td>
                <td>{source.notes || "-"}</td>
                <td><SourceActions sourceId={source.id} trackingStatus={source.tracking_status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="section">
        <ReviewForm resources={resources} />
      </section>

      <section className="section card">
        <h2>任务日志</h2>
        <table className="table">
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
                <td>{task.status}</td>
                <td>{task.summary}</td>
              </tr>
            ))}
            {tasks.length === 0 ? (
              <tr>
                <td colSpan={4}>暂无任务</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </>
  );
}
