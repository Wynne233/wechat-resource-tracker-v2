"use client";

import { useState, useTransition } from "react";

import { API_BASE, type SearchResource } from "@/lib/api";

export function ReviewForm({ resources }: { resources: SearchResource[] }) {
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  function submit(formData: FormData) {
    const resourceId = String(formData.get("resource_id") ?? "");
    const payload = {
      canonical_name: String(formData.get("canonical_name") ?? "") || null,
      summary: String(formData.get("summary") ?? "") || null,
      current_status: String(formData.get("current_status") ?? "") || null,
      risk_level: String(formData.get("risk_level") ?? "") || null,
      risk_notes: String(formData.get("risk_notes") ?? "") || null,
      note: String(formData.get("note") ?? ""),
    };
    startTransition(async () => {
      setMessage("");
      try {
        const response = await fetch(`${API_BASE}/admin/resources/${resourceId}/review`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error("修正失败");
        }
        const data = await response.json();
        setMessage(`修正成功，重算评分 ${data.score.total_score}/${data.score.grade}`);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "修正失败");
      }
    });
  }

  return (
    <form action={submit} className="card form">
      <div className="card-heading">
        <h2>资源人工修正</h2>
        <span className="badge">基础能力</span>
      </div>
      <select className="select" name="resource_id" required>
        <option value="">选择资源</option>
        {resources.map((resource) => (
          <option key={resource.id} value={resource.id}>
            {resource.canonical_name}
          </option>
        ))}
      </select>
      <input className="input" name="canonical_name" placeholder="新标准名，可选" />
      <textarea className="textarea" name="summary" placeholder="新简介，可选" />
      <div className="split">
        <select className="select" name="current_status" defaultValue="">
          <option value="">状态不变</option>
          <option value="available">可用</option>
          <option value="review">待复核</option>
          <option value="suspected_down">疑似失效</option>
          <option value="down">已失效</option>
          <option value="suspected_update">疑似更新</option>
        </select>
        <select className="select" name="risk_level" defaultValue="">
          <option value="">风险不变</option>
          <option value="low">低风险</option>
          <option value="medium">中风险</option>
          <option value="high">高风险</option>
        </select>
      </div>
      <input className="input" name="risk_notes" placeholder="风险备注，可选" />
      <input className="input" name="note" placeholder="修正说明" />
      <button className="button warn" disabled={isPending} type="submit">
        {isPending ? "修正中..." : "保存修正并重算评分"}
      </button>
      {message ? <p className="muted">{message}</p> : null}
    </form>
  );
}

