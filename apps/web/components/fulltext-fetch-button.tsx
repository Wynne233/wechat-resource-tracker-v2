"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { fetchArticleFulltext } from "@/lib/api";

export function FulltextFetchButton() {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  function submit() {
    startTransition(async () => {
      setMessage("");
      try {
        const result = await fetchArticleFulltext(30);
        setMessage(
          `已尝试补抓 ${result.requested_count} 篇，成功 ${result.imported_count} 篇，跳过 ${result.skipped_count} 篇，生成/更新 ${result.resource_count} 个资源。`,
        );
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "全文补抓失败，请确认 wechat-article-exporter 正在运行。");
      }
    });
  }

  return (
    <div className="analysis-result">
      <h2>全文补抓</h2>
      <p className="muted">对缺少正文的文章调用 exporter 下载正文，成功后重新进入资源解析。</p>
      <button className="button" disabled={isPending} onClick={submit} type="button">
        {isPending ? "补抓并解析中..." : "补抓缺失全文"}
      </button>
      {message ? <p className="muted">{message}</p> : null}
    </div>
  );
}
