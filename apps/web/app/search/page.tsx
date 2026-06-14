import Link from "next/link";

import { SubscribeButton } from "@/components/subscribe-button";
import { searchResources } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = "" } = await searchParams;
  const result = await searchResources(q);

  return (
    <>
      <section className="section-header">
        <div>
          <span className="badge">搜索结果</span>
          <h1 className="section-title">{q || "未输入关键词"}</h1>
          <p className="section-subtitle">{result.message}</p>
        </div>
        {q ? <SubscribeButton displayName={`${q} 主题`} targetType="topic" targetValue={q} /> : null}
      </section>

      {result.items.length === 0 ? (
        <section className="card">
          <h2>当前资源库暂无相关资源</h2>
          <p className="muted">这不是系统无法工作，而是冷启动数据还没有覆盖这个主题。你可以先订阅关键词，后续导入或同步到相关资源时会进入站内通知。</p>
        </section>
      ) : (
        <section className="section list">
          {result.items.map((item) => (
            <article className="card resource-card" key={item.id}>
              <div className="row">
                <div>
                  <Link href={`/resources/${item.id}`}>
                    <h2>{item.canonical_name}</h2>
                  </Link>
                  <p className="muted">{item.summary}</p>
                </div>
                <div>
                  <div className="score">{item.latest_score.toFixed(1)}</div>
                  <span className="badge">{item.latest_grade}</span>
                </div>
              </div>
              <div className="meta">
                <span className={`status ${item.current_status}`}>{item.current_status}</span>
                <span>{item.source_count} 个公众号来源</span>
                <span>{item.mention_count} 条证据</span>
                <span>风险：{item.risk_level}</span>
              </div>
              {item.capability_tags.length ? (
                <div className="meta">
                  {item.capability_tags.slice(0, 6).map((tag) => (
                    <span className="badge" key={tag}>{tag}</span>
                  ))}
                </div>
              ) : null}
              {item.match_reason ? <p className="muted">命中原因：{item.match_reason}</p> : null}
              <p className="muted">{item.explanation}</p>
              <div className="meta">
                <Link className="button secondary" href={`/resources/${item.id}`}>
                  查看详情
                </Link>
                <SubscribeButton displayName={item.canonical_name} targetType="resource" targetValue={item.id} />
              </div>
            </article>
          ))}
        </section>
      )}
    </>
  );
}
