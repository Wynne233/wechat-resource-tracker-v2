"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { analyzeArticleUrl, type ArticleAnalyzeResponse } from "@/lib/api";

export function ArticleUrlAnalyzeForm({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const [articleUrl, setArticleUrl] = useState("");
  const [result, setResult] = useState<ArticleAnalyzeResponse | null>(null);
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  function submit() {
    startTransition(async () => {
      setMessage("");
      setResult(null);
      try {
        const data = await analyzeArticleUrl(articleUrl);
        setResult(data);
        setMessage(data.message);
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "文章分析失败，请检查链接或全文获取服务。");
      }
    });
  }

  return (
    <div className={compact ? "analysis-panel form" : "article-analyzer form"}>
      <div className="panel-heading">
        <div>
          <h2>分析公众号文章链接</h2>
          <p>粘贴单篇公众号文章，系统会抓取正文、识别资源、入库并追踪来源。</p>
        </div>
        <span className="status configured">自动追踪</span>
      </div>
      <div className="search-box wide">
        <input
          className="input"
          onChange={(event) => setArticleUrl(event.target.value)}
          placeholder="https://mp.weixin.qq.com/s/..."
          value={articleUrl}
        />
        <button className="button" disabled={isPending || !articleUrl.trim()} onClick={submit} type="button">
          {isPending ? "分析中..." : "开始分析"}
        </button>
      </div>
      {message ? <p className="muted">{message}</p> : null}
      {result ? (
        <div className="analysis-result">
          <div className="meta">
            <span>文章：{result.article_title || "未识别标题"}</span>
            <span>公众号：{result.source_name || "待补全"}</span>
            <span>全文：{result.content_status}</span>
            <span>解析：{result.extraction_status}</span>
            <span>追踪：{result.tracking_status}</span>
          </div>
          <div className="meta">
            <span>新增资源 {result.created_resources}</span>
            <span>更新资源 {result.updated_resources}</span>
            <span>通知 {result.notifications_created}</span>
          </div>
          {result.resources.length ? (
            <div className="list">
              {result.resources.map((resource) => (
                <div className="mini-resource" key={resource.id}>
                  <div>
                    <Link className="text-link" href={`/resources/${resource.id}`}>
                      {resource.canonical_name}
                    </Link>
                    <p className="muted">{resource.summary}</p>
                  </div>
                  <span className="badge">
                    {resource.latest_score.toFixed(1)} / {resource.latest_grade}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">本次没有生成资源。若全文状态不是 full_text，请先确保全文获取服务可用后重新分析。</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
