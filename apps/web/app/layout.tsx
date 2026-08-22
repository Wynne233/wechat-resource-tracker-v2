import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "公众号资源发现与追踪助手",
  description: "搜索、评分、追溯和管理公众号文章中出现的资源。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <main className="shell">
          <nav className="nav">
            <Link className="brand" href="/">
              资源情报库
            </Link>
            <Link href="/">搜索</Link>
            <Link href="/subscriptions">订阅中心</Link>
            <Link href="/settings">通知设置</Link>
            <Link href="/admin">管理后台</Link>
          </nav>
          {children}
        </main>
      </body>
    </html>
  );
}
