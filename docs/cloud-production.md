# Cloud production deployment

The original Render deployment only published the web UI and API. Its API used
ephemeral SQLite and pointed the collector integrations to `127.0.0.1`, which
means it could not independently run article collection or weekly tracking.

`render.cloud.yaml` is the complete production topology:

| Service | Responsibility | Persistence |
| --- | --- | --- |
| `wechat-resource-tracker-web` | Public product UI | None required |
| `wechat-resource-tracker-api` | Article processing, DeepSeek extraction, resource DB, Feishu settings | 1 GB disk |
| `wechat-article-exporter-tracker` | Single article full-text fetcher | Stateless |
| `wewe-rss-tracker` | WeChat login session and new-article discovery | 1 GB disk |
| `wechat-resource-tracker-weekly-check` | Runs the product's weekly sync, full-text fetch, extraction and notifications | Calls the API once per week |

The scheduled jobs use UTC. `30 18 * * 6` is Sunday 02:30 in China, and
wewe-rss refreshes its feed 30 minutes earlier. The delay and weekly cadence
are intentional to limit WeChat requests.

## Required one-time configuration

1. In Render, create a new Blueprint from this repository and choose
   `render.cloud.yaml`. The API and wewe-rss services need a paid Starter plan
   because their data and WeChat login session must survive restarts. The
   scheduled job also has a minimum monthly charge on Render.
2. When Render asks for secrets, set `DEEPSEEK_API_KEY`, a strong `AUTH_CODE`,
   and the same long random `SCHEDULER_TOKEN` on both the API and cron service.
3. Open the deployed wewe-rss URL, enter the configured auth code, scan to log
   in, then add the public accounts to track. This session lives on its
   persistent disk, not on the local computer.
4. In the product's notification settings, save and test a Feishu bot webhook.
   It is stored in the API's persistent database and is never shown again.
5. Paste an article URL in the product. Successful analyses automatically add
   the source to the weekly tracking pool.

## Operational checks

- API health: `https://wechat-resource-tracker-api.onrender.com/health`
- Article analysis: paste a new `mp.weixin.qq.com/s/...` URL in the product.
- Weekly job: use Render's **Trigger Run** once after wewe-rss has a logged-in
  account and a configured feed.
- Feishu: use the product's **Send test** action, then inspect the incoming bot
  message.

The article URL path still has a direct WeChat-page fallback. It is only a
backup for a temporary exporter failure; the normal production route is
article URL -> exporter -> DeepSeek extraction.
