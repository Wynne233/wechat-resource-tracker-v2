import Link from "next/link";

import { getNotifications, getSubscriptions } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SubscriptionsPage() {
  const [subscriptions, notifications] = await Promise.all([getSubscriptions(), getNotifications()]);

  return (
    <>
      <section className="section-header">
        <div>
          <span className="badge">订阅中心</span>
          <h1 className="section-title">主题、资源和通知</h1>
          <p className="section-subtitle">订阅命中后先进入站内通知；外部飞书推送由通知设置决定。</p>
        </div>
      </section>

      <section className="section grid two">
        <div className="card">
          <h2>我的订阅</h2>
          <div className="list">
            {subscriptions.length === 0 ? <p className="muted">暂无订阅。可以在搜索结果或资源详情页订阅。</p> : null}
            {subscriptions.map((item) => (
              <div className="card" key={item.id}>
                <div className="row">
                  <strong>{item.display_name}</strong>
                  <span className="badge">{item.target_type}</span>
                </div>
                <p className="muted">{item.target_value}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h2>站内通知</h2>
          <div className="list">
            {notifications.length === 0 ? <p className="muted">暂无通知。导入命中订阅的资源后会生成记录。</p> : null}
            {notifications.map((item) => (
              <div className="card" key={item.id}>
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
