# Deployment

Green Nova AI is two processes. It has no dependency on a particular host name, domain, tunnel or cloud provider.

| Process | Command | Listens on | Exposure |
|---|---|---|---|
| Backend (FastAPI, **one worker**) | `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-server-header` (cwd = repo root) | `127.0.0.1:8000` | **Internal only.** Never publish it. |
| Web (Next.js) | `npm run build && npm start` in `web/` | `0.0.0.0:3000` | Put your TLS-terminating reverse proxy / platform in front. |

The browser only ever talks to the web server. The web server calls the backend server-side through an explicit allow-list (`web/src/app/api/gn`), and refuses any `BACKEND_URL` that is not a loopback address.
The results that the application shows are precomputed files in `models/*/outputs/<region-id>/`, so no GPU, no model training and no raw datasets are needed to run it.

## Option A – a VM or server (Linux or Windows)
1. Install Python 3.10–3.12 and Node.js ≥ 20.9. `pip install -r requirements.txt` (CPU only) and `cd web && npm ci`.
2. Configure (see `.env.example`, `web/.env.example`):
   * `NEXT_PUBLIC_SITE_URL=https://your.public.url` – **set it before `npm run build`**, it is inlined at build time.
   * `GREEN_NOVA_DATA=/var/lib/green-nova` – a writable folder; the job database and results live in `<GREEN_NOVA_DATA>/runtime` (back it up if you want completed analyses to survive).
3. Run both processes under a supervisor of your choice (systemd, Windows service/Task Scheduler, pm2, supervisord). Example systemd units:
   ```ini
   # /etc/systemd/system/green-nova-backend.service
   [Service]
   WorkingDirectory=/opt/green-nova
   Environment=GREEN_NOVA_DATA=/var/lib/green-nova
   ExecStart=/opt/green-nova/.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-server-header
   Restart=always
   # /etc/systemd/system/green-nova-web.service
   [Service]
   WorkingDirectory=/opt/green-nova/web
   Environment=BACKEND_URL=http://127.0.0.1:8000
   ExecStart=/usr/bin/npm start
   Restart=always
   ```
4. Reverse proxy with HTTPS to `127.0.0.1:3000`. Caddy example (`Caddyfile`): `your.public.url { reverse_proxy 127.0.0.1:3000 }`. nginx: `proxy_pass http://127.0.0.1:3000;` plus `proxy_set_header X-Forwarded-For $remote_addr;`.
   The proxy **must overwrite** `X-Forwarded-For` (or `CF-Connecting-IP` if you use Cloudflare): rate limiting keys on it, and without a proxy it is client-controlled.
5. Health: `GET /health` (liveness) and `GET /ready` (per-governorate model availability) on the backend, `GET /` on the web server.

## Option B – containers
```bash
docker compose up --build        # web on http://localhost:3000
```
`docker-compose.yml` builds `deploy/Dockerfile.backend` and `deploy/Dockerfile.web`. The web container joins the backend container's network namespace (`network_mode: "service:backend"`), so `127.0.0.1:8000` is shared between them and only port 3000 is published. A named volume keeps the job database. Set `NEXT_PUBLIC_SITE_URL` as a build argument: `docker compose build --build-arg NEXT_PUBLIC_SITE_URL=https://your.public.url web`.

## Updating or adding results
The committed outputs are produced by `scripts/build_governorate.ps1 -Region jo-irbid,...` (needs the data cache described in `docs/DATA_SOURCES.md`; one-off downloads take hours, then each governorate takes seconds to minutes). The backend re-reads output files when they change, no restart is needed. `scripts/summarize_governorates.py` regenerates `docs/GOVERNORATES.md` from them.

## Security checklist
* Backend bound to loopback and not published; `/docs`, `/openapi.json`, `/admin` are not served.
* The web server sets CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`; HTTPS/HSTS belong in your proxy.
* No secrets are used by the application. Never commit `.env` files; only the `.env.example` templates are tracked.
* Inputs are validated (region ids, polygon ids, geometry size/area/vertices, body size) and per-client rate limits and a memory guard protect the backend.
