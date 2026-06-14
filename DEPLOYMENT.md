# 部署上线速查

## 推荐路径

前端用 Vercel，后端用 Render，数据库后续接 Supabase Postgres。

这样做的原因：

- Vercel 很适合 Next.js 前端，部署快，简历链接好看。
- Render/Fly/Railway 更适合 FastAPI 常驻后端。
- Supabase 适合把本地 SQLite 升级成线上 Postgres，但不是第一步必须项。

## 1. 后端：Render

1. 把项目推到 GitHub。
2. 打开 Render，New > Blueprint，选择仓库根目录。
3. Render 会读取 `render.yaml`，创建 `wechat-resource-tracker-api`。
4. 部署成功后确认：

```text
https://你的-render-api域名/health
```

返回：

```json
{"status":"ok"}
```

## 2. 前端：Vercel

1. 打开 Vercel，New Project，选择同一个 GitHub 仓库。
2. Root Directory 选择：

```text
wechat-resource-tracker-v2/apps/web
```

如果仓库根目录就是 `wechat-resource-tracker-v2`，则选择：

```text
apps/web
```

3. 添加环境变量：

```text
NEXT_PUBLIC_API_BASE_URL=https://你的-render-api域名
INTERNAL_API_BASE_URL=https://你的-render-api域名
```

4. Deploy。

## 3. Supabase 数据库，可稍后做

如果只做简历 demo，可以先用后端镜像内置的 SQLite 示例库。

如果要长期保存用户新增数据：

1. Supabase 新建 Project。
2. Project Settings > Database，复制 connection string。
3. 在 Render 后端服务里添加：

```text
DATABASE_URL=postgresql://postgres:你的密码@你的host:5432/postgres
```

4. 重新部署后端。

## 4. 当前线上能力边界

稳定适合放简历：

- 搜索资源
- 查看资源详情
- 查看来源追溯
- 查看状态时间线
- 查看订阅、通知、后台演示界面

谨慎开放：

- 输入真实公众号链接触发采集
- 配置真实通知 webhook

原因是公众号全文采集依赖 exporter/wewe-rss 的登录态和采集服务，免费云平台上不一定稳定。
