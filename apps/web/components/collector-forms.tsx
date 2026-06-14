"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { API_BASE, type IntegrationConfig } from "@/lib/api";

const exporterSample = `[
  {
    "source_name": "效率工具研究所",
    "title": "最近值得收藏的 AI 效率工具合集",
    "article_url": "https://mp.weixin.qq.com/s/demo-ai-tools",
    "published_at": "2026-05-08 09:30:00",
    "content_text": "Notion AI 是一个 AI 工具，适合整理知识库，官网 https://www.notion.so/product/ai。Raycast AI 适合 macOS 快速启动、脚本和 AI 问答，下载页 https://www.raycast.com。",
    "read_count": 3200,
    "like_count": 140,
    "comment_count": 12
  }
]`;

type ImportResponse = {
  requested_count: number;
  imported_count: number;
  skipped_count: number;
  resource_count: number;
};

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail ?? "请求失败");
  }
  return data as T;
}

function resultText(data: ImportResponse) {
  return `完成：读取 ${data.requested_count} 篇，新增 ${data.imported_count} 篇，跳过 ${data.skipped_count} 篇，生成/更新 ${data.resource_count} 个资源`;
}

export function WechatExporterImportForm() {
  const [content, setContent] = useState(exporterSample);
  const [fileName, setFileName] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  function importContent() {
    startTransition(async () => {
      setMessage("");
      try {
        const data = await postJson<ImportResponse>("/admin/imports/wechat-exporter", {
          content,
          file_name: fileName,
          source_name: sourceName,
        });
        setMessage(resultText(data));
        window.location.reload();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "导入失败");
      }
    });
  }

  async function readFile(file: File | null) {
    if (!file) return;
    setFileName(file.name);
    setContent(await file.text());
  }

  return (
    <div className="card form">
      <div className="card-heading">
        <h2>历史冷启动导入</h2>
        <span className="badge">wechat-article-exporter</span>
      </div>
      <p className="muted">
        本地导出工具：
        <a className="text-link" href="http://127.0.0.1:4100" target="_blank" rel="noreferrer">
          打开 wechat-article-exporter
        </a>
        。登录公众号后台后导出 JSON/HTML，再在这里导入。
      </p>
      <div className="split">
        <input className="input" value={sourceName} onChange={(event) => setSourceName(event.target.value)} placeholder="默认公众号名，可选" />
        <input className="input" type="file" accept=".json,.html,.htm,.md,.txt,.csv" onChange={(event) => readFile(event.target.files?.[0] ?? null)} />
      </div>
      <textarea className="textarea tall" value={content} onChange={(event) => setContent(event.target.value)} />
      <div className="row">
        <button className="button" disabled={isPending} onClick={importContent} type="button">
          {isPending ? "导入中..." : "导入历史文章"}
        </button>
        {fileName ? <span className="muted">当前文件：{fileName}</span> : null}
      </div>
      {message ? <p className="muted">{message}</p> : null}
    </div>
  );
}

export function WeweRssSyncForm({ integration }: { integration?: IntegrationConfig }) {
  const router = useRouter();
  const [baseUrl, setBaseUrl] = useState(integration?.base_url ?? "");
  const [feedUrl, setFeedUrl] = useState(integration?.feed_url ?? "");
  const [authCode, setAuthCode] = useState("");
  const [message, setMessage] = useState(integration?.last_message ?? "");
  const [isPending, startTransition] = useTransition();

  const status = useMemo(() => integration?.status ?? "not_configured", [integration]);

  function saveConfig() {
    startTransition(async () => {
      setMessage("");
      try {
        const data = await postJson<IntegrationConfig>("/admin/integrations/wewe-rss", {
          base_url: baseUrl,
          feed_url: feedUrl,
          auth_code: authCode,
        });
        setMessage(data.last_message);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "保存失败");
      }
    });
  }

  function syncNow() {
    startTransition(async () => {
      setMessage("");
      try {
        const data = await postJson<ImportResponse>("/admin/sync/wewe-rss", { feed_url: feedUrl });
        setMessage(resultText(data));
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "同步失败");
      }
    });
  }

  return (
    <div className="card form">
      <div className="card-heading">
        <h2>增量同步</h2>
        <span className={`status ${status}`}>{status}</span>
      </div>
      <p className="muted">
        本地同步工具：
        <a className="text-link" href="http://127.0.0.1:4000/dash" target="_blank" rel="noreferrer">
          打开 wewe-rss 管理台
        </a>
        。扫码登录微信读书并添加公众号后，再回到这里同步；系统会读取最新文章列表，但只新增以前没入库的文章。
      </p>
      <input className="input" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="wewe-rss 服务地址，可选" />
      <input className="input" value={feedUrl} onChange={(event) => setFeedUrl(event.target.value)} placeholder="JSON/RSS Feed 地址" />
      <input className="input" value={authCode} onChange={(event) => setAuthCode(event.target.value)} placeholder="鉴权码，可选" />
      <div className="row">
        <button className="button secondary" disabled={isPending} onClick={saveConfig} type="button">
          保存配置
        </button>
        <button className="button" disabled={isPending || !feedUrl} onClick={syncNow} type="button">
          {isPending ? "处理中..." : "立即同步"}
        </button>
      </div>
      {message ? <p className="muted">{message}</p> : null}
    </div>
  );
}

export function SupplementImportForm() {
  const [sourceName, setSourceName] = useState("");
  const [articleUrl, setArticleUrl] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  function submit() {
    startTransition(async () => {
      setMessage("");
      try {
        const data = await postJson<ImportResponse>("/admin/imports/supplement", {
          source_name: sourceName,
          article_url: articleUrl,
          title,
          content,
        });
        setMessage(resultText(data));
        window.location.reload();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "导入失败");
      }
    });
  }

  return (
    <div className="card form">
      <div className="card-heading">
        <h2>补充导入</h2>
        <span className="badge">文件 / 链接</span>
      </div>
      <div className="split">
        <input className="input" value={sourceName} onChange={(event) => setSourceName(event.target.value)} placeholder="公众号名称" />
        <input className="input" value={articleUrl} onChange={(event) => setArticleUrl(event.target.value)} placeholder="文章链接或唯一标识" />
      </div>
      <input className="input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="文章标题，可选" />
      <textarea className="textarea" value={content} onChange={(event) => setContent(event.target.value)} placeholder="正文文本或 HTML" />
      <button className="button warn" disabled={isPending || !sourceName || !articleUrl || !content} onClick={submit} type="button">
        {isPending ? "导入中..." : "导入补充文章"}
      </button>
      {message ? <p className="muted">{message}</p> : null}
    </div>
  );
}
