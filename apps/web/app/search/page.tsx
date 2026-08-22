import Link from "next/link";

import { SubscribeButton } from "@/components/subscribe-button";
import { searchResources } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = "" } = await searchParams;
  const result = await searchResources(q);

  return (
    <>
      <section className="admin-hero">
        <div>
          <h1>{q || "搜索资源"}</h1>
          <p>{result.message}</p>
        </div>
        {q ? <SubscribeButton displayName={`${q} 主题`} targetType="topic" targetValue={q} /> : null}
      </section>

      {result.items.length === 0 ? (
        <section className="ops-panel section">
          <h2>资源库暂无相关结果</h2>
          <p className="muted">这通常意味着演示数据未覆盖该主题，或相关文章尚未导入。你可以订阅关键词，后续命中时会生成通知。</p>
        </section>
      ) : (
        <section className="section list">
          {result.items.map((item) => (
            <article className="ops-panel resource-card" key={item.id}>
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
                <span>{item.source_count} 个来源</span>
                <span>{item.mention_count} 条证据</span>
                <span>风险：{item.risk_level}</span>
              </div>
              {item.capability_tags.length ? (
                <div className="tag-row">
                  {item.capability_tags.slice(0, 6).map((tag) => (
                    <span className="tag" key={tag}>{tag}</span>
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
