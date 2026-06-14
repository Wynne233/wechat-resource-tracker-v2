"use client";

import { useState, useTransition } from "react";

import { API_BASE, type FeishuSetting } from "@/lib/api";

export function FeishuForm({ initial }: { initial: FeishuSetting }) {
  const [setting, setSetting] = useState(initial);
  const [webhook, setWebhook] = useState("");
  const [isPending, startTransition] = useTransition();

  function test() {
    startTransition(async () => {
      const response = await fetch(`${API_BASE}/notification-settings/feishu/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ webhook_url: webhook }),
      });
      setSetting(await response.json());
    });
  }

  function save() {
    startTransition(async () => {
      const response = await fetch(`${API_BASE}/notification-settings/feishu`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ webhook_url: webhook }),
      });
      setSetting(await response.json());
    });
  }

  return (
    <div className="card form">
      <h2>飞书 Webhook</h2>
      <p className="muted">站内通知默认开启。飞书只需要自定义机器人 Webhook，不做 OAuth。</p>
      <input className="input" onChange={(event) => setWebhook(event.target.value)} placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." value={webhook} />
      <div className="meta">
        <button className="button secondary" disabled={isPending} onClick={test} type="button">
          发送测试
        </button>
        <button className="button" disabled={isPending} onClick={save} type="button">
          保存配置
        </button>
      </div>
      <div className="card">
        <div>状态：{setting.status}</div>
        <div>Webhook：{setting.masked_webhook || "未配置"}</div>
        <div className="muted">{setting.last_test_result || "尚未测试"}</div>
      </div>
    </div>
  );
}

