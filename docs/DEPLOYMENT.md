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

## Option B - containers (Docker Compose)
Requirements: Docker Engine / Docker Desktop with Compose v2.20 or newer, about 8 GB RAM for the Docker VM, 2 GB of disk for the images. No other tool and no download is needed: the models, checkpoints and precomputed governorate results are in the repository.
```bash
git clone https://github.com/Jafar-Al/green-nova.git && cd green-nova
cp .env.example .env              # optional: every setting has a default (see "Docker Compose" in .env.example)
docker compose up --build --wait  # builds both images, starts them and returns when both are healthy
```
Open <http://localhost:3000>. Stop with `docker compose down` (the job database survives; `docker compose down -v` also deletes it).

How it is built and wired (`docker-compose.yml`, `deploy/Dockerfile.backend`, `deploy/Dockerfile.web`):
* **Images.** Both are multi-stage and run as a non-root user with a read-only root file system (`/tmp` is a tmpfs). The backend image (Python 3.11, about 1.4 GB, mostly the geospatial and ML libraries) holds the code, the model checkpoints, the per-governorate runtime stacks and the committed outputs (about 200 MB); raw datasets are never in an image. The web image (Next.js standalone, about 440 MB) is built with `web/` as its context. To serve different results, change `models/*/outputs` and rebuild, or bind-mount a folder over `/app/models/<model>/outputs`.
* **Network.** The backend container joins the web container's network namespace: the backend listens on `127.0.0.1:8000` inside it (never published; the web server only talks to loopback) and only the web port is published. The web container owns the namespace because it is the stable one, so a crashed backend is restarted by Docker (`restart: unless-stopped`) and the web server reconnects by itself.
* **Health.** The backend is healthy only when `/ready` reports status `ready` (the Python libraries import, every governorate has its checkpoint, runtime stack and outputs). The web container is healthy only when its proxy gets an answer from the backend, so `--wait` returns when the whole application can serve results. `GET /health` is plain liveness.
* **State.** Job database, job results and logs live in the named volume `green-nova-data` (`/data`). Bind mounts must be writable by uid 10001.
* **Settings.** `NEXT_PUBLIC_SITE_URL` is inlined at build time (rebuild after changing it); the backend limits (`GN_MIN_FREE_MB`, `GN_JOB_RATE_PER_HOUR`, `GN_MAX_QUEUE`) and the host port (`GREEN_NOVA_PORT`) are read at start. Behind a TLS proxy follow Option A step 4.
* **Restarts.** `docker compose restart`, `docker compose up -d` after a change and a backend crash are all handled. If you restart only the web container with a bare `docker restart`, also restart the backend (`docker compose restart web` does both); the backend shares the web container's network namespace.

Verified on Docker Desktop 29 (Windows 11, WSL 2): image builds, `docker compose up --wait`, `scripts/verify_stack.py --web http://127.0.0.1:3000` for all 12 governorates (boundaries, polygons, layers, GeoTIFF clips and a real Model 2 job in the container), restart, down/up with the job still readable from the volume, and recovery after killing the backend process.

## Updating or adding results
The committed outputs are produced by `scripts/build_governorate.ps1 -Region jo-irbid,...` (needs the data cache described in `docs/DATA_SOURCES.md`; one-off downloads take hours, then each governorate takes seconds to minutes). The backend re-reads output files when they change, no restart is needed. `scripts/summarize_governorates.py` regenerates `docs/GOVERNORATES.md` from them.

## Security checklist
* Backend bound to loopback and not published; `/docs`, `/openapi.json`, `/admin` are not served.
* The web server sets CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`; HTTPS/HSTS belong in your proxy.
* No secrets are used by the application. Never commit `.env` files; only the `.env.example` templates are tracked.
* Inputs are validated (region ids, polygon ids, geometry size/area/vertices, body size) and per-client rate limits and a memory guard protect the backend.
