"use client";

import { useState, useTransition } from "react";

import { API_BASE } from "@/lib/api";

const sample = `[
  {
    "source_name": "效率工具研究所",
    "source_identifier": "efficiency-lab",
    "title": "最近值得收藏的 AI 效率工具合集",
    "article_url": "https://mp.weixin.qq.com/s/demo-ai-tools",
    "published_at": "2026-05-08T09:30:00",
    "content_text": "Notion AI 是一个 AI 工具，适合整理知识库，官网 https://www.notion.so/product/ai。Raycast AI 适合 macOS 快速启动、脚本和 AI 问答，下载页 https://www.raycast.com。",
    "content_html": "",
    "read_count": 3200,
    "like_count": 140,
    "comment_count": 12,
    "crawl_source": "history_export",
    "raw_payload": {}
  }
]`;

export function HistoryImportForm() {
  const [jsonText, setJsonText] = useState(sample);
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  function submit() {
    startTransition(async () => {
      setMessage("");
      try {
        const articles = JSON.parse(jsonText);
        const response = await fetch(`${API_BASE}/admin/imports/history-json`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ articles }),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail ?? "导入失败");
        }
        setMessage(`导入完成：文章 ${data.imported_count}，跳过 ${data.skipped_count}，资源 ${data.resource_count}`);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "导入失败");
      }
    });
  }

  return (
    <div className="card form">
      <div className="card-heading">
        <h2>历史文章 JSON 导入</h2>
        <span className="badge">标准文章对象</span>
      </div>
      <p className="muted">先把不同采集来源转成统一 JSON，再进入文章去重、抽取、归一、评分和订阅通知。</p>
      <textarea className="textarea" value={jsonText} onChange={(event) => setJsonText(event.target.value)} />
      <button className="button" disabled={isPending} onClick={submit} type="button">
        {isPending ? "导入中..." : "导入并分析"}
      </button>
      {message ? <p className="muted">{message}</p> : null}
    </div>
  );
}

