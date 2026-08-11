# WeChat Download API for IRA

This local service fetches public WeChat Official Account articles. It is bound
to `127.0.0.1` and keeps WeChat login credentials outside Git.

## Start

1. Copy `wechat.env.template` to `wechat.env`.
2. From this directory run `docker compose -f compose.yml up -d`.
3. Open <http://127.0.0.1:5000/login.html> and scan with the administrator of a
   WeChat Official Account. The upstream project reports that login credentials
   normally remain valid for about four days.
4. Open <http://127.0.0.1:5000/rss.html>, search for accounts and subscribe.
5. Trigger a poll in the UI or call `POST /api/rss/poll`.

## Connect subscriptions to IRA

Add each subscribed account to `config/wechat_sources.json` using its `fakeid`,
IRA ticker and destination folder. Then run:

```bash
.venv/bin/python scripts/ops/sync_wechat_articles.py
```

The script performs cursor-based incremental synchronization, writes the source
Markdown to `data/inputs/news/<folder>/wechat/`, and invokes IRA's existing
LanceDB ingestion pipeline. Articles from unmapped accounts are not ingested.

## Optional MCP

Set `ENABLE_MCP=1` and a long random `MCP_TOKEN` in the gitignored `wechat.env`,
then restart the container. The streamable HTTP endpoint is
`http://127.0.0.1:5000/mcp` and requires `Authorization: Bearer <MCP_TOKEN>`.

Only fetch public articles you are entitled to archive and observe publisher
copyright, platform terms and conservative request rates.
