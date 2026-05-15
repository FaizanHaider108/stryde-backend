# Deploy Stryde backend

Set the same variables as in `backend/.env.example` on your host (Render, Railway, Fly.io, VPS).  
**Do not commit `.env`** — it contains secrets.

## Required for a working API

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET` | Signs access tokens |
| `ALGORITHM` | Usually `HS256` |
| `RESET_TOKEN_SECRET` | Signs password-reset tokens |
| `BACKEND_PUBLIC_URL` | Public API URL, e.g. `https://stryde-api.onrender.com` |

## Auth & users

| Variable | Purpose |
|----------|---------|
| `REFRESH_TOKEN_EXPIRE_DAYS` | Default `45` |
| `RESET_TOKEN_EXPIRE_MINUTES` | Default `60` |
| `RESET_PASSWORD_URL` | App deep link, e.g. `stride://screens/setPassword` |
| `PASSWORD_RESET_SUBJECT` | Email subject line |
| `APPLE_CLIENT_ID` | iOS bundle id; production: `com.strydelabs.app` only |

Optional: `RESET_PASSWORD_DEEP_LINK`, `RESET_PASSWORD_EMAIL_URL`

## Email (password reset)

| Variable | Purpose |
|----------|---------|
| `SMTP_HOST` | e.g. `smtp.gmail.com` |
| `SMTP_PORT` | e.g. `587` |
| `SMTP_USER` | Sender account |
| `SMTP_PASS` | App password / SMTP password |
| `SMTP_USE_TLS` | `true` / `false` |
| `SMTP_USE_SSL` | `false` for typical Gmail |

## File uploads

| Variable | Purpose |
|----------|---------|
| `AWS_ACCESS_KEY` | S3 access key |
| `AWS_SECRET_KEY` | S3 secret |
| `AWS_REGION` | e.g. `ap-south-1` |
| `AWS_S3_BUCKET` | Bucket name |

If AWS vars are empty, uploads go to local `uploads/` (not ideal on Render — use S3).

## Routes & AI plans

| Variable | Purpose |
|----------|---------|
| `GRAPHHOPPER_API_KEY` | Route / routing API |
| `GLM_API_KEY` | Training plan AI |
| `GLM_REQUEST_TIMEOUT` | Seconds, e.g. `120` |
| `GLM_API_URL` | Optional override |
| `GLM_MODEL` | Optional override |

## Push notifications

| Variable | Purpose |
|----------|---------|
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Path to service account JSON inside the container, or mount as secret file |

On Render: upload JSON as a **secret file** or paste into env and adjust code — default expects a file at `./stride-b2956-....json` in `backend/`.

## Stripe

| Variable | Purpose |
|----------|---------|
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_PRICE_ID` | Subscription price id |
| `APP_SCHEME` | Deep link scheme, e.g. `stride` |

## Server / CORS

| Variable | Purpose |
|----------|---------|
| `UVICORN_HOST` | Local dev: `0.0.0.0` |
| `UVICORN_PORT` | Local dev port, e.g. `8888` |
| `PORT` | Set by Render/Railway in production |
| `CORS_ALLOWED_ORIGINS` | Optional; `*` for mobile |

## Deploy error: `DuplicateTable: relation "clubs" already exists`

This means Postgres **already has tables**, but Alembic thinks no migration ran (empty `alembic_version`).

**Fix (one time)** — in Render **Shell** for the service, from `/app`:

```bash
alembic stamp head
alembic upgrade head
```

Or redeploy after pulling the latest `Dockerfile` (startup script stamps head automatically when it detects existing tables).

**Fresh database:** create a new empty Postgres on Render and point `DATABASE_URL` to it, then deploy.

---

## Deploy on Render (Docker)

1. Create **PostgreSQL** on Render → copy **Internal/External Database URL** → `DATABASE_URL`.
2. **New Web Service** → root directory **`backend`** → Docker.
3. Health check: `/api/v1/health`.
4. Add **every** variable from the tables above in the **Environment** tab (match your local `backend/.env` names).
5. Set `BACKEND_PUBLIC_URL` to the Render URL (https).
6. Deploy.

```bash
curl https://YOUR-SERVICE.onrender.com/api/v1/health
```

## Point the mobile app

`app/.env`:

```env
EXPO_PUBLIC_API_BASE_URL=https://YOUR-SERVICE.onrender.com
```

Restart Expo with `npx expo start --clear`.  
Also set the same value in `app/eas.json` → `production.env` for store builds.

## Variables that stay in the app only (`app/.env`)

These are **not** read by the Python backend:

- `EXPO_PUBLIC_GOOGLE_*`
- `EXPO_PUBLIC_FIREBASE_*`
- `EXPO_PUBLIC_API_BASE_URL` (app → calls backend)

Your `backend/.env` may list Google client IDs for convenience; only the Expo app uses them.
