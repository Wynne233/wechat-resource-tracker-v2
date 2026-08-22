import { FeishuForm } from "@/components/feishu-form";
import { getFeishuSetting } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const setting = await getFeishuSetting();

  return (
    <>
      <section className="admin-hero">
        <div>
          <h1>通知设置</h1>
          <p>站内通知默认生成；飞书 Webhook 用于把资源命中、状态变化和风险提示推送到外部协作空间。</p>
        </div>
      </section>
      <section className="admin-grid section">
        <div className="ops-panel">
          <h2>站内通知</h2>
          <p className="muted">订阅命中的资源会先写入站内通知。暂停追踪的来源不会产生来源维度提醒。</p>
          <span className="status available">已启用</span>
        </div>
        <FeishuForm initial={setting} />
      </section>
    </>
  );
}
