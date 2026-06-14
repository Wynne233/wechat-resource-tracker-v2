"use client";

import { useState, useTransition } from "react";

import { API_BASE } from "@/lib/api";

export function SourceForm() {
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  function submit(formData: FormData) {
    const payload = {
      name: String(formData.get("name") ?? ""),
      source_identifier: String(formData.get("source_identifier") ?? "") || null,
      source_type: String(formData.get("source_type") ?? "wechat"),
      trust_level: String(formData.get("trust_level") ?? "pending"),
      notes: String(formData.get("notes") ?? ""),
    };
    startTransition(async () => {
      setMessage("");
      try {
        const response = await fetch(`${API_BASE}/admin/sources`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error("保存来源失败");
        }
        setMessage("已保存来源，刷新后可见。");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "保存来源失败");
      }
    });
  }

  return (
    <form action={submit} className="card form">
      <div className="card-heading">
        <h2>新增公众号来源</h2>
        <span className="badge">P0</span>
      </div>
      <input className="input" name="name" placeholder="公众号名称" required />
      <input className="input" name="source_identifier" placeholder="公众号标识，可选" />
      <div className="split">
        <select className="select" name="source_type" defaultValue="wechat">
          <option value="wechat">微信公众号</option>
          <option value="rss">RSS</option>
        </select>
        <select className="select" name="trust_level" defaultValue="pending">
          <option value="high">高可信</option>
          <option value="medium">中可信</option>
          <option value="low">低可信</option>
          <option value="pending">待评估</option>
          <option value="blacklist">黑名单</option>
        </select>
      </div>
      <textarea className="textarea" name="notes" placeholder="备注" />
      <button className="button" disabled={isPending} type="submit">
        {isPending ? "保存中..." : "保存来源"}
      </button>
      {message ? <p className="muted">{message}</p> : null}
    </form>
  );
}

