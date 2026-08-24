import Link from "next/link";

import { ArticleUrlAnalyzeForm } from "@/components/article-url-analyze-form";

const examples = ["AI 工具", "免费听歌", "PDF 工具", "图片高清化", "API 文档", "稍后读"];

export default function HomePage() {
  return (
    <>
      <section className="home-hero">
        <div className="hero-copy">
          <h1>把公众号文章变成可管理的资源情报库</h1>
          <p>
            搜索资源、查看来源证据、跟踪状态变化，并把重要更新推送到站内和飞书。文章只是证据，资源才是主角。
          </p>
          <form action="/search" className="search-box">
            <input className="input" name="q" placeholder="例如：免费听歌、AI 工具、PDF 工具" required />
            <button className="button" type="submit">搜索资源</button>
          </form>
          <div className="meta">
            {examples.map((item) => (
              <Link className="badge" href={`/search?q=${encodeURIComponent(item)}`} key={item}>
                {item}
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <ArticleUrlAnalyzeForm />
      </section>

      <section className="feature-grid">
        <div>
          <h2>资源质量判断</h2>
          <p>综合多来源、证据、风险、状态和新鲜度评分，避免只看到过时文章列表。</p>
        </div>
        <div>
          <h2>来源追溯</h2>
          <p>每个资源都能回到公众号、文章标题、发布时间和证据片段。</p>
        </div>
        <div>
          <h2>通知闭环</h2>
          <p>站内通知默认可用，飞书 Webhook 可真实发送测试和资源命中提醒。</p>
        </div>
      </section>
    </>
  );
}
