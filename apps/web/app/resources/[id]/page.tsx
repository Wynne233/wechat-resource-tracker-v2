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
    ["多源推荐分", resource.score.multi_source_score],
    ["公众号可信度分", resource.score.source_trust_score],
    ["互动热度分", resource.score.interaction_score],
    ["时间新鲜度分", resource.score.freshness_score],
    ["状态可用分", resource.score.availability_score],
    ["证据完整度分", resource.score.evidence_score],
    ["风险扣分", -resource.score.risk_penalty],
  ];

  return (
    <>
      <section className="section-header">
        <div>
          <span className={`status ${resource.current_status}`}>{resource.current_status}</span>
          <h1 className="section-title">{resource.canonical_name}</h1>
          <p className="section-subtitle">{resource.summary}</p>
        </div>
        <SubscribeButton displayName={resource.canonical_name} targetType="resource" targetValue={resource.id} />
      </section>

      <section className="section grid two">
        <div className="card">
          <div className="card-heading">
            <h2>为什么推荐它</h2>
            <div>
              <div className="score">{resource.score.total_score.toFixed(1)}</div>
              <span className="badge">{resource.score.grade}</span>
            </div>
          </div>
          <p className="muted">{resource.score.explanation}</p>
          <table className="table">
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

        <div className="card">
          <h2>基础信息</h2>
          <div className="list">
            <div>类型：{resource.resource_type}</div>
            <div>平台：{resource.platforms.length ? resource.platforms.join("、") : "未标注"}</div>
            <div>别名：{resource.aliases.length ? resource.aliases.join("、") : "无"}</div>
            <div>风险：{resource.risk_level} {resource.risk_notes}</div>
            <div className="list">
              {resource.links.map((link) => (
                <a className="button secondary" href={link} key={link} rel="noreferrer" target="_blank">
                  打开资源链接
                </a>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="section card">
        <h2>来源追溯</h2>
        <table className="table">
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
                  <a href={source.article_url} rel="noreferrer" target="_blank">
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

      <section className="section card">
        <h2>状态时间线</h2>
        <div className="list">
          {resource.timeline.map((item) => (
            <div className="card" key={`${item.checked_at}-${item.change_summary}`}>
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
