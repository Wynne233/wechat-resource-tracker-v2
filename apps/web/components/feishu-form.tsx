"use client";

import { useState, useTransition } from "react";

import { API_BASE, type FeishuSetting } from "@/lib/api";

export function FeishuForm({ initial }: { initial: FeishuSetting }) {
  const [setting, setSetting] = useState(initial);
  const [webhook, setWebhook] = useState("");
  const [isPending, startTransition] = useTransition();

  async function post(path: string) {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ webhook_url: webhook }),
    });
    if (!response.ok) {
      throw new Error("请求失败，请检查 Webhook 地址。");
    }
    setSetting(await response.json());
  }

  function test() {
    startTransition(async () => {
      try {
        await post("/notification-settings/feishu/test");
      } catch (error) {
        setSetting((current) => ({ ...current, status: "test_failed", last_test_result: error instanceof Error ? error.message : "测试失败" }));
      }
    });
  }

  function save() {
    startTransition(async () => {
      try {
        await post("/notification-settings/feishu");
      } catch (error) {
        setSetting((current) => ({ ...current, status: "invalid", last_test_result: error instanceof Error ? error.message : "保存失败" }));
      }
    });
  }

  return (
    <div className="ops-panel form">
      <div className="panel-heading">
        <div>
          <h2>飞书 Webhook</h2>
          <p>保存自定义机器人 Webhook 后，测试按钮会真实发送消息；订阅命中时也会同步推送。</p>
        </div>
        <span className={`status ${setting.status}`}>{setting.status}</span>
      </div>
      <input
        className="input"
        onChange={(event) => setWebhook(event.target.value)}
        placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
        value={webhook}
      />
      <div className="meta">
        <button className="button secondary" disabled={isPending || !webhook.trim()} onClick={test} type="button">
          发送测试消息
        </button>
        <button className="button" disabled={isPending || !webhook.trim()} onClick={save} type="button">
          保存 Webhook
        </button>
      </div>
      <div className="analysis-result">
        <div>Webhook：{setting.masked_webhook || "未配置"}</div>
        <div className="muted">{setting.last_test_result || "尚未测试"}</div>
      </div>
    </div>
  );
}
