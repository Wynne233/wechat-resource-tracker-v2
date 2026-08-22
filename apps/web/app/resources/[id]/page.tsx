import Link from "next/link";
import { notFound } from "next/navigation";

import { SubscribeButton } from "@/components/subscribe-button";
import { getResource } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResourcePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let resource;
  try {
    resource = await getResource(id);
  } catch {
    notFound();
  }

  const scoreRows = [
    ["多来源推荐", resource.score.multi_source_score],
    ["来源可信度", resource.score.source_trust_score],
    ["互动热度", resource.score.interaction_score],
    ["时间新鲜度", resource.score.freshness_score],
    ["状态可用性", resource.score.availability_score],
    ["证据完整度", resource.score.evidence_score],
    ["风险扣分", -resource.score.risk_penalty],
  ];

  return (
    <>
      <section className="admin-hero">
        <div>
          <span className={`status ${resource.current_status}`}>{resource.current_status}</span>
          <h1>{resource.canonical_name}</h1>
          <p>{resource.summary}</p>
        </div>
        <SubscribeButton displayName={resource.canonical_name} targetType="resource" targetValue={resource.id} />
      </section>

      <section className="admin-grid section">
        <div className="ops-panel">
          <div className="panel-heading">
            <h2>为什么推荐它</h2>
            <div>
              <div className="score">{resource.score.total_score.toFixed(1)}</div>
              <span className="badge">{resource.score.grade}</span>
            </div>
          </div>
          <p className="muted">{resource.score.explanation}</p>
          <table className="resource-table compact">
            <tbody>
              {scoreRows.map(([label, value]) => (
                <tr key={label}>
                  <td>{label}</td>
                  <td>{Number(value).toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="ops-panel">
          <h2>基础信息</h2>
          <div className="ops-list">
            <div><span>类型</span><strong>{resource.resource_type}</strong></div>
            <div><span>平台</span><strong>{resource.platforms.length ? resource.platforms.join("、") : "未标注"}</strong></div>
            <div><span>别名</span><strong>{resource.aliases.length ? resource.aliases.join("、") : "无"}</strong></div>
            <div><span>风险</span><strong>{resource.risk_level} {resource.risk_notes}</strong></div>
          </div>
          <div className="tag-row">
            {resource.capability_tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
          </div>
          <div className="list">
            {resource.links.map((link) => (
              <a className="button secondary" href={link} key={link} rel="noreferrer" target="_blank">
                打开资源链接
              </a>
            ))}
          </div>
        </div>
      </section>

      <section className="admin-section">
        <div className="section-heading">
          <h2>来源追溯</h2>
          <p>每条证据都来自文章原文，用于判断资源是否真实被推荐或提及。</p>
        </div>
        <table className="resource-table">
          <thead>
            <tr>
              <th>公众号</th>
              <th>文章</th>
              <th>证据片段</th>
              <th>置信度</th>
            </tr>
          </thead>
          <tbody>
            {resource.sources.map((source) => (
              <tr key={`${source.article_url}-${source.evidence_snippet}`}>
                <td>
                  {source.source_name}
                  <div className="muted">{source.source_trust_level}</div>
                </td>
                <td>
                  <a className="text-link" href={source.article_url} rel="noreferrer" target="_blank">
                    {source.article_title}
                  </a>
                  <div className="muted">{source.published_at?.slice(0, 10) ?? "时间未知"}</div>
                </td>
                <td>{source.evidence_snippet}</td>
                <td>{Math.round(source.confidence * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="admin-section">
        <div className="section-heading">
          <h2>状态时间线</h2>
          <p>状态变化来自后续文章语义或人工复核，不把资源官网临时访问失败当成失效证据。</p>
        </div>
        <div className="list">
          {resource.timeline.map((item) => (
            <div className="analysis-result" key={`${item.checked_at}-${item.change_summary}`}>
              <div className="row">
                <strong>{item.checked_at.slice(0, 16).replace("T", " ")}</strong>
                <span className={`status ${item.result_status}`}>{item.result_status}</span>
              </div>
              <p>{item.change_summary}</p>
              <p className="muted">{item.suggestion}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <Link className="button secondary" href="/search?q=AI">
          返回搜索
        </Link>
      </section>
    </>
  );
}
