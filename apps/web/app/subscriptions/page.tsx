import Link from "next/link";

import { getNotifications, getSubscriptions } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SubscriptionsPage() {
  const [subscriptions, notifications] = await Promise.all([getSubscriptions(), getNotifications()]);

  return (
    <>
      <section className="admin-hero">
        <div>
          <h1>订阅与通知</h1>
          <p>订阅主题、资源或来源后，命中的资源变化会先进入站内通知，再按设置推送到飞书。</p>
        </div>
      </section>

      <section className="admin-grid section">
        <div className="ops-panel">
          <h2>我的订阅</h2>
          <div className="list">
            {subscriptions.length === 0 ? <p className="muted">暂无订阅。可以在搜索结果或资源详情页订阅。</p> : null}
            {subscriptions.map((item) => (
              <div className="analysis-result" key={item.id}>
                <div className="row">
                  <strong>{item.display_name}</strong>
                  <span className="badge">{item.target_type}</span>
                </div>
                <p className="muted">{item.target_value}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="ops-panel">
          <h2>站内通知</h2>
          <div className="list">
            {notifications.length === 0 ? <p className="muted">暂无通知。导入命中订阅的资源后会生成记录。</p> : null}
            {notifications.map((item) => (
              <div className="analysis-result" key={item.id}>
                <div className="row">
                  <strong>{item.title}</strong>
                  <span className="badge">{item.status}</span>
                </div>
                <p>{item.body}</p>
                {item.resource_id ? (
                  <Link className="button secondary" href={`/resources/${item.resource_id}`}>
                    查看资源
                  </Link>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
