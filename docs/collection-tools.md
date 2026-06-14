# 数据采集工具配置

本项目按 PRD 第 9 章接入三层数据获取：

- `wechat-article-exporter`：历史冷启动导入，源码位于 `external/wechat-article-exporter`，本地端口 `4100`。
- `wewe-rss`：重点公众号增量同步，源码位于 `external/wewe-rss`，本地端口 `4000`，默认 Feed 为 `http://127.0.0.1:4000/feeds/all.json`。
- 补充导入：在管理后台粘贴单篇文章正文或 HTML。

## 当前本机状态

- 已从 GitHub 拉取两个工具源码。
- 本机没有 Docker，当前使用源码版部署。
- `wechat-article-exporter` 已通过 npm 安装依赖并完成 Nuxt 生产构建，运行在 `http://127.0.0.1:4100`。
- `wewe-rss` 已通过 pnpm 安装依赖，dashboard 与 server 均已构建，运行在 `http://127.0.0.1:4000`。
- `wewe-rss` 的 Prisma schema engine 在当前 Windows/Node 24 环境下迁移报错，因此脚本直接执行官方迁移 SQL 初始化 SQLite 表；数据库位于 Windows 可写临时目录。

## 命令

```powershell
npm run tools:prepare
npm run tools:wechat-exporter
npm run tools:wewe-rss
npm run dev:product
```

如果安装 Docker，可直接运行：

```powershell
docker compose -f docker-compose.external-tools.yml up
```

管理后台地址：

- 产品后台：`http://127.0.0.1:3000/admin`
- wechat-article-exporter：`http://127.0.0.1:4100`
- wewe-rss：`http://127.0.0.1:4000`
