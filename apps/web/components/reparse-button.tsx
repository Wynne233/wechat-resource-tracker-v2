"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { reparseAllArticles } from "@/lib/api";

export function ReparseButton() {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  function submit() {
    startTransition(async () => {
      setMessage("");
      try {
        const result = await reparseAllArticles();
        setMessage(`已重新解析 ${result.requested_count} 篇文章，生成/更新 ${result.resource_count} 个资源。`);
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "重新解析失败");
      }
    });
  }

  return (
    <div className="analysis-result">
      <h2>资源解析修复</h2>
      <p className="muted">按当前抽取规则重新解析已有文章，用于修复旧数据中的泛词资源和漏识别。</p>
      <button className="button warn" disabled={isPending} onClick={submit} type="button">
        {isPending ? "重新解析中..." : "重新解析全部文章"}
      </button>
      {message ? <p className="muted">{message}</p> : null}
    </div>
  );
}
