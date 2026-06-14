import { FeishuForm } from "@/components/feishu-form";
import { getFeishuSetting } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const setting = await getFeishuSetting();

  return (
    <>
      <section className="section-header">
        <div>
          <span className="badge">通知设置</span>
          <h1 className="section-title">站内默认开启，飞书可选</h1>
          <p className="section-subtitle">P0 只做飞书 Webhook，不做飞书 OAuth，不读取用户飞书账号。</p>
        </div>
      </section>
      <section className="section grid two">
        <div className="card">
          <h2>站内通知</h2>
          <p className="muted">所有命中订阅的事件默认生成站内通知，包括主题新增资源、资源疑似失效、资源疑似更新等。</p>
          <span className="status available">已开启</span>
        </div>
        <FeishuForm initial={setting} />
      </section>
    </>
  );
}
