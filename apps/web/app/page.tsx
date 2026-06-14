import Link from "next/link";

import { ArticleUrlAnalyzeForm } from "@/components/article-url-analyze-form";

const examples = ["AI 工具", "免费听歌", "追剧", "PPT 工具", "图片处理", "网盘"];

export default function HomePage() {
  return (
    <>
      <section className="hero">
        <span className="badge">网页输入 → 网页输出 → 订阅追踪</span>
        <h1>从公众号文章里找到可信、可追溯的资源</h1>
        <p>
          输入关键词，搜索已入库的公众号资源实体库。结果会展示质量分、来源证据、当前状态和风险提示，而不是把文章列表直接丢给你。
        </p>
        <form action="/search" className="search-box">
          <input className="input" name="q" placeholder="例如：免费听歌、AI 工具、追剧 App" required />
          <button className="button" type="submit">
            搜索资源
          </button>
        </form>
        <div className="meta">
          {examples.map((item) => (
            <Link className="badge" href={`/search?q=${encodeURIComponent(item)}`} key={item}>
              {item}
            </Link>
          ))}
        </div>
      </section>

      <section className="section">
        <ArticleUrlAnalyzeForm />
      </section>

      <section className="section grid three">
        <div className="card">
          <h2>质量判断</h2>
          <p className="muted">按多源推荐、来源可信度、互动热度、新鲜度、可用状态和证据完整度评分。</p>
        </div>
        <div className="card">
          <h2>来源追溯</h2>
          <p className="muted">每个资源都能回到公众号、文章标题、发布时间和提及片段。</p>
        </div>
        <div className="card">
          <h2>订阅提醒</h2>
          <p className="muted">主题或资源后续有变化时，优先生成站内通知，可选飞书 Webhook。</p>
        </div>
      </section>
    </>
  );
}
