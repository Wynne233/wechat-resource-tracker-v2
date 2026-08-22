# Oracle Always Free deployment

This deployment runs the complete product on one Ubuntu ARM VM:

- Product UI at `http://PUBLIC_IP/`
- `wewe-rss` admin UI at `http://PUBLIC_IP:4000/`
- API, exporter, article database, and `wewe-rss` database stay on private Docker networks
- Docker volumes preserve the product database and WeChat login session across restarts
- Host cron invokes the existing weekly tracking job each Sunday at 02:30

## Prepare the VM

Use an Oracle Always Free Ubuntu ARM instance with at least 2 OCPU and 6 GB
memory. Add ingress rules for TCP `22`, `80`, `443`, and `4000` in the Oracle
security list. On the server, install Docker Engine and the Docker Compose
plugin, then clone this repository into `/opt/wechat-resource-tracker-v2`.

## Configure and start

```bash
cd /opt/wechat-resource-tracker-v2/deploy/oracle
cp .env.example .env
nano .env
docker compose up -d --build
./install-weekly-cron.sh /opt/wechat-resource-tracker-v2
```

The `PUBLIC_HOST` value must be the actual public IP before opening wewe-rss.
Set a strong private `WEWE_RSS_AUTH_CODE`, then open port 4000 in a browser,
enter that code, and use the wewe-rss UI to scan and add accounts.

## Verify

```bash
docker compose ps
docker compose exec api python -m app.jobs weekly-source-check
```

For the product, open `http://PUBLIC_IP/`, save and test the Feishu webhook in
Settings, then paste a real article URL. The normal flow is exporter -> AI
extraction. Direct WeChat parsing remains a temporary fallback.

## Domain and HTTPS

The product works on an IP address for initial testing. For a professional
resume link, point a domain's DNS A record to the VM, replace `:80` in
`Caddyfile` with that domain name, and restart the gateway:

```bash
docker compose restart gateway
```

Caddy then manages HTTPS automatically. Do not expose the API or exporter to
the public internet.
