# X GIF Downloader Bot

A production-ready monorepo for an X (Twitter) GIF downloader:

- `bot/` polls mentions with the X API v2, finds the parent post's animated GIF or video, and replies with a download link.
- `web/` is a FastAPI app with a mobile-first dark UI, an instant MP4 proxy download, on-the-fly ffmpeg GIF conversion, ad slots, and a support CTA.

```
gif-twitter-bot/
├── .env.example
├── .gitignore
├── README.md
├── docker-compose.yml
├── requirements.txt
├── data/
│   └── .gitkeep
├── bot/
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── config.py
│   ├── main.py
│   ├── media.py
│   ├── requirements.txt
│   └── state.py
└── web/
    ├── .dockerignore
    ├── Dockerfile
    ├── app.py
    ├── config.py
    ├── media.py
    ├── requirements.txt
    ├── static/
    │   ├── app.js
    │   ├── favicon.svg
    │   └── styles.css
    └── templates/
        ├── base.html
        ├── download.html
        ├── error.html
        ├── index.html
        ├── privacy.html
        └── terms.html
```

## How it works

1. A user replies to a public post containing an animated GIF or video and mentions the bot.
2. The bot calls `GET /2/users/:id/mentions` with `since_id` from SQLite.
3. It expands the mentioned post's `referenced_tweets.id` and `referenced_tweets.id.attachments.media_keys`.
4. It finds the parent `animated_gif` or `video` media and selects the highest-bitrate MP4 variant.
5. It atomically claims the mention in SQLite, then replies with `BASE_WEB_URL/download?url=...&tweet_id=...`.
6. The web app validates the URL against an X media host allowlist, shows a video preview, and offers:
   - `/download/mp4?url=...` — streams the original MP4 with `Content-Disposition: attachment`.
   - `/convert?url=...` — downloads to a temp directory, converts with ffmpeg `palettegen`/`paletteuse`, and streams the GIF. Successful conversions are cached on disk by a hash of the source video (plus the conversion settings), so repeat requests for the same clip — even from different tweets — are served without re-downloading or re-encoding.

### Mentions that are ignored

The bot does not spend a reply on:

- Mentions that are not replies.
- Replies whose parent post is deleted, protected, or missing from the response.
- Parent posts without `animated_gif` or `video` media.
- Parents whose media is longer than `MAX_VIDEO_DURATION_SECONDS` (default 5, `0` = no limit). X reports `duration_ms` in the mentions response, so this costs no bandwidth.
- Parents without an MP4 variant.
- Mentions from the bot account itself.
- Mentions skipped after the daily reply limit is reached.

### At-most-once processing

A mention row is inserted before any reply is attempted. If the process crashes after the claim but before the reply, the mention is not retried automatically. This deliberately trades a rare missed reply for a guarantee that the bot never double-replies or double-charges for the same mention. Delete the row from `processed_mentions` if you need to manually retry a specific mention.

### Cost and rate-limit controls

- `since_id` is persisted in SQLite and only advances after a complete poll.
- SQLite deduplicates mentions across restarts and pagination.
- `POLL_INTERVAL_SECONDS` controls read volume.
- `DAILY_REPLY_LIMIT` caps write cost.
- `MAX_MENTION_PAGES` prevents runaway backlog pagination.
- `MENTION_BATCH_SIZE` is the API page size (maximum 100).
- `429 Too Many Requests` uses the `x-rate-limit-reset` header with exponential backoff and jitter.
- `BOOTSTRAP_ON_FIRST_RUN=true` starts from the newest existing mention so a fresh install does not reply to old mentions.

## Requirements

- Python 3.12+
- ffmpeg for GIF conversion
- Docker and Docker Compose (recommended for deployment)
- An X developer project with API access that permits reading mentions and creating posts

## Create the X app

1. Create a project and app in the [X Developer Portal](https://developer.x.com/).
2. Set up **OAuth 1.0a User Context** with **Read and Write** permissions.
3. Generate the API key/secret and the access token/secret for the bot account.
4. Generate the app-only **Bearer Token**.
5. Find the bot's numeric user ID:

```bash
curl -s "https://api.x.com/2/users/by/username/YOUR_BOT_USERNAME" \
  -H "Authorization: Bearer $X_BEARER_TOKEN"
```

Copy `.env.example` to `.env` and fill in every required value.

> The bot must log in as the account it reads mentions for. The access token must belong to the same account as `BOT_USER_ID`.

## Local development

### 1. Install ffmpeg (and gifsicle)

Windows (PowerShell):

```powershell
winget install --id Gyan.FFmpeg -e
winget install --id Gyan.Gifsicle -e
```

macOS:

```bash
brew install ffmpeg gifsicle
```

Ubuntu / Debian:

```bash
sudo apt update && sudo apt install -y ffmpeg gifsicle
```

gifsicle is optional: when present, converted GIFs are post-optimized with
`-O3 --lossy`, which usually cuts file size by 30-60%. Set `GIFSICLE_BINARY=off`
to disable it.

Verify with:

```bash
ffmpeg -version
gifsicle --version
```

### 2. Create the environment file

PowerShell:

```powershell
Copy-Item .env.example .env
```

Bash:

```bash
cp .env.example .env
```

Edit `.env` and set the X credentials, `BOT_USER_ID`, and `BOT_HANDLE`.

### 3. Install dependencies

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Bash:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Run the web app

```bash
uvicorn app:app --app-dir web --host 127.0.0.1 --port 8000 --reload
```

Open http://localhost:8000 and http://localhost:8000/healthz.

### 5. Run the bot

In a second terminal, with the same virtual environment active:

```bash
python bot/main.py
```

The first run initializes `data/state.db` and records the newest existing mention so old mentions are skipped.

### 6. Test the full flow

Reply to a public post with a GIF and mention the bot. The bot should reply with a link like:

```
http://localhost:8000/download?url=https%3A%2F%2Fvideo.twimg.com%2F...mp4&tweet_id=...
```

If the bot account is not yet reachable from the public internet, the link will still work locally in a browser on the same machine.

## Docker Compose

The included Compose file builds both services, gives the bot a persistent `/data` volume, gives the web service a persistent `/cache` volume for converted GIFs, and waits for the web health check.

```bash
cp .env.example .env
docker compose up --build -d
docker compose logs -f
```

Open http://localhost:8000.

Stop:

```bash
docker compose down
```

Stop and delete the bot's mention state:

```bash
docker compose down -v
```

Important production settings before deploying:

```dotenv
BASE_WEB_URL=https://your-domain.example
PUBLIC_BASE_URL=https://your-domain.example
TRUST_PROXY_HEADERS=true
```

Leave `TRUST_PROXY_HEADERS=false` if the container is exposed directly, because a spoofed `X-Forwarded-For` would bypass per-IP conversion limits.

## Deployment

### Railway or Render

Create two services from the same repository:

**Web service**

- Root directory: `web`
- Build: Dockerfile
- Port: `8000`
- Health check path: `/healthz`
- Environment: `SITE_NAME`, `PUBLIC_BASE_URL`, `ALLOWED_MEDIA_HOSTS`, ad/support settings

**Bot service**

- Root directory: `bot`
- Build: Dockerfile
- No public port
- Environment: all X credentials, `BOT_USER_ID`, `BASE_WEB_URL` (the public web URL), `DATABASE_PATH=/data/state.db`
- Attach a persistent volume at `/data`

Set `BOOTSTRAP_ON_FIRST_RUN=true` for the first deployment. Set `BASE_WEB_URL` to the public HTTPS URL of the web service before starting the bot.

### DigitalOcean / VPS

1. Create an Ubuntu VPS and point a domain at it.
2. Install Docker and the Compose plugin.
3. Clone the repository and copy `.env.example` to `.env`.
4. Set `BASE_WEB_URL` and `PUBLIC_BASE_URL` to your HTTPS domain.
5. Run `docker compose up --build -d`.
6. Put Caddy or Nginx in front of port 8000 for TLS.

Example Caddyfile:

```caddyfile
gif.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

With a reverse proxy, set `TRUST_PROXY_HEADERS=true` only if the proxy sanitizes inbound `X-Forwarded-For` headers and always sets them.

## Environment reference

| Variable | Purpose | Default |
| --- | --- | --- |
| `X_API_KEY` | OAuth 1.0a consumer key | required |
| `X_API_SECRET` | OAuth 1.0a consumer secret | required |
| `X_ACCESS_TOKEN` | Bot account access token | required |
| `X_ACCESS_SECRET` | Bot account access token secret | required |
| `X_BEARER_TOKEN` | App bearer token | required |
| `BOT_USER_ID` | Numeric ID of the bot account | required |
| `BASE_WEB_URL` | URL inserted into replies | required |
| `PUBLIC_BASE_URL` | Canonical URL for the web app | `BASE_WEB_URL` |
| `DATABASE_PATH` | SQLite database path | `./data/state.db` |
| `POLL_INTERVAL_SECONDS` | Mention poll interval | `60` |
| `MENTION_BATCH_SIZE` | Mentions per API page, 5–100 | `100` |
| `MAX_MENTION_PAGES` | Backlog pagination cap | `10` |
| `DAILY_REPLY_LIMIT` | Replies per UTC day, `0` = unlimited | `100` |
| `MAX_VIDEO_DURATION_SECONDS` | Ignore parent media longer than this, `0` = no limit | `5` |
| `BOOTSTRAP_ON_FIRST_RUN` | Skip old mentions on first start | `true` |
| `BOT_HANDLE` | Bot handle without `@` | empty |
| `SITE_NAME` | Brand name in the UI | `GIFGrab` |
| `CONTACT_EMAIL` | Contact link in legal pages | empty |
| `BUY_ME_A_COFFEE_URL` | Support CTA destination | BMAC homepage |
| `ALLOWED_MEDIA_HOSTS` | Comma-separated CDN allowlist | `video.twimg.com,pbs.twimg.com` |
| `MAX_MEDIA_BYTES` | Upstream MP4 size cap | `31457280` |
| `MAX_GIF_BYTES` | Converted GIF size cap | `104857600` |
| `GIF_MAX_WIDTH` | Output GIF width cap | `640` |
| `GIF_FPS` | Output GIF frame rate | `15` |
| `FFMPEG_TIMEOUT_SECONDS` | Conversion timeout | `120` |
| `GIFSICLE_BINARY` | Post-optimizer binary, `off` = disable | `gifsicle` |
| `GIF_LOSSY` | gifsicle `--lossy` level, `0` = lossless `-O3` only | `60` |
| `MAX_CONCURRENT_CONVERSIONS` | Simultaneous conversions | `2` |
| `CONVERT_RATE_LIMIT_PER_MINUTE` | Per-IP conversion limit, `0` = unlimited | `5` |
| `DOWNLOAD_RATE_LIMIT_PER_MINUTE` | Per-IP MP4 proxy limit, `0` = unlimited | `60` |
| `GIF_CACHE_DIR` | On-disk cache root, `off` = disable | `./data/gif-cache` |
| `GIF_CACHE_MAX_BYTES` | Evict oldest cached GIFs above this size, `0` = unlimited | `2147483648` |
| `TRUST_PROXY_HEADERS` | Honor `X-Forwarded-For` | `false` |
| `LOG_LEVEL` | Bot and web log level | `INFO` |

## Endpoints

| Endpoint | Description |
| --- | --- |
| `GET /` | Landing page |
| `GET /download?url=<encoded_mp4>&tweet_id=<id>` | Preview and download UI |
| `GET /download/mp4?url=<encoded_mp4>&tweet_id=<id>` | Proxied MP4 with attachment headers |
| `GET /convert?url=<encoded_mp4>&tweet_id=<id>` | GIF conversion (disk-cached by video hash) |
| `GET /healthz` | Liveness / ffmpeg check |
| `GET /privacy`, `GET /terms` | Legal pages |

The web app only accepts HTTPS URLs on hosts listed in `ALLOWED_MEDIA_HOSTS`, with paths ending in `.mp4`, no credentials, and port 443. Redirects are re-validated. This prevents the proxy and converter from being used as an SSRF primitive.

## Monetization

Three ad containers are already positioned and styled:

1. **Top banner** — `#ad-top` on the landing and download pages.
2. **In-content native ad** — `#ad-native`.
3. **Bottom banner** — `#ad-bottom`.

Paste your AdSense or Adsterra script and container markup inside the marked `<div>` elements. The Content-Security-Policy in `web/app.py` allows common Google ad domains and Adsterra. If your network uses additional domains, update `CSP` in `web/app.py`.

For AdSense:

- Add your site to AdSense and complete verification.
- Publish an `ads.txt` file at the domain root with your publisher record.
- Set `CONTACT_EMAIL` so the privacy policy has a real contact.
- Add a consent management platform if you serve personalized ads in the EEA/UK.
- Keep the privacy policy accurate for the ad networks you enable.

The **Buy me a coffee** CTA appears under the download controls and on the landing page when `BUY_ME_A_COFFEE_URL` is set.

## Operational notes

- SQLite runs in WAL mode, so keep the bot volume on local disk, not a network filesystem.
- Run one bot replica per SQLite database. Multiple replicas with separate volumes could reply to the same mention.
- Run one web worker by default. The conversion semaphore and per-IP limiter are in-process. Scale horizontally by running multiple containers behind a proxy, not by adding uvicorn workers.
- `MAX_MEDIA_BYTES` applies to the upstream MP4. `MAX_GIF_BYTES` applies after conversion.
- Temporary conversion directories are removed after the response. The web app also purges stale `xgif-*` directories at startup and once per hour, which covers crashes and disconnected clients.
- Converted GIFs are cached under `GIF_CACHE_DIR`, keyed by `sha256(source video) + GIF_FPS + GIF_MAX_WIDTH + optimizer settings`. A normalized-URL alias table avoids re-downloading the MP4 on repeat hits; the content hash deduplicates the same clip posted from different tweets. The cache is bounded by `GIF_CACHE_MAX_BYTES` and evicts the oldest entries hourly. Keep it on local disk, and give it a persistent volume in production.
- Cached GIF responses are sent with `Cache-Control: public, max-age=31536000, immutable`, so browsers and a CDN in front of the app can reuse them without hitting the origin. Generated convert links carry a `v=` cache-busting token derived from the conversion settings, so changing `GIF_FPS`, `GIF_MAX_WIDTH`, or the optimizer config invalidates public caches automatically.
- When `gifsicle` is installed, each ffmpeg result is post-optimized with `-O3 --lossy=$GIF_LOSSY`. This is best-effort: if gifsicle is missing, fails, or produces a larger file, the original ffmpeg output is kept.
- The `/healthz` endpoint returns `503` if ffmpeg is missing, so orchestrators will not route traffic to a broken converter. It also reports `gifsicle` availability without degrading health.

## Troubleshooting

**Bot starts but never replies**

- Check `BOT_USER_ID` is the numeric ID of the token owner.
- Confirm the app has OAuth 1.0a user context with Read and Write.
- The mention must be a reply to a post with `animated_gif` or `video` media.
- Check `docker compose logs bot` or the local terminal output.

**`401 Unauthorized` or `403 Forbidden`**

- Regenerate the access token after changing app permissions.
- Make sure the token belongs to the same account as `BOT_USER_ID`.

**`429 Too Many Requests`**

- The bot handles it automatically and logs the wait time.
- Increase `POLL_INTERVAL_SECONDS`, lower `MENTION_BATCH_SIZE`, or reduce `DAILY_REPLY_LIMIT`.

**GIF conversion fails**

- Run `ffmpeg -version` inside the container: `docker compose exec web ffmpeg -version`.
- Check `docker compose logs web`.
- Try the MP4 download to confirm the source media is reachable.

**Video preview does not load**

- The media URL may be expired or region-restricted.
- Confirm `video.twimg.com` is in `ALLOWED_MEDIA_HOSTS`.
- The MP4 download endpoint can still work even if the browser preview fails.

## Legal

Downloading media does not grant you rights to it. Respect copyright, X's terms, and the original creator's wishes. This project is not affiliated with X Corp.
