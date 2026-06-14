# 公众号资源发现与追踪助手 V2

全新目录隔离重构版本。旧项目不删除、不复用业务代码。

## 技术栈

- `apps/api`: FastAPI + SQLAlchemy + SQLite
- `apps/web`: Next.js + TypeScript
- `sample_data`: 冷启动 JSON 示例文章

## 本地运行

后端：

```bash
cd apps/api
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：

```bash
cd apps/web
npm install
npm run dev
```

默认前端读取 `http://127.0.0.1:8000`。当前沙箱环境默认使用共享内存 SQLite，进程重启后数据会清空；可通过 `DATABASE_URL` 覆盖为可写 SQLite 文件或 Postgres。
