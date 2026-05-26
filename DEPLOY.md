# Deploy Stryde backend

Copy the variables from `.env.example` into your host (Render, Railway, Fly.io, or a VPS).

Do not commit `.env` — it contains secrets.

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
| `RESET_PASSWORD_URL` | App deep link, e.g. `stryde://screens/setPassword` |
| `PASSWORD_RESET_SUBJECT` | Email subject line |
| `APPLE_CLIENT_ID` | iOS bundle id; production: `com.strydelabs.app` only |

## Google OAuth (Expo Go backend broker)

| Variable | Purpose |
|----------|---------|
| `GOOGLE_OAUTH_CLIENT_ID` | Web OAuth client ID from Google Cloud |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Web OAuth client secret |
| `GOOGLE_OAUTH_PUBLIC_URL` | Optional on Render if `BACKEND_PUBLIC_URL` is already `https://…` |

**Google Cloud Console** → Web client → Authorized redirect URI (exact):

```
https://stryde-backend-ts25.onrender.com/api/v1/auth/google/callback
```

**Mobile app** (`app/.env`) for Expo Go while API stays on LAN:

```env
EXPO_PUBLIC_API_BASE_URL=http://YOUR_LAN_IP:8000
EXPO_PUBLIC_OAUTH_API_BASE_URL=https://stryde-backend-ts25.onrender.com
```

Verify after deploy:

```bash
curl -I "https://stryde-backend-ts25.onrender.com/api/v1/auth/google/start?app_return=test&after_path=/home"
# Expect: HTTP/1.1 302 (not 404)
```

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

On Render: upload JSON as a **secret file** or paste into env and adjust code — default expects a file at `./stryde-firebase-adminsdk.json` in `backend/`.

## Stripe

| Variable | Purpose |
|----------|---------|
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_PRICE_ID` | Subscription price id |
| `APP_SCHEME` | Deep link scheme, e.g. `stryde` |

## Server / CORS

| Variable | Purpose |
|----------|---------|
| `UVICORN_HOST` | Local dev: `0.0.0.0` |
| `UVICORN_PORT` | Local dev port, e.g. `8888` |
| `PORT` | Set by Render/Railway in production |
| `CORS_ALLOWED_ORIGINS` | Optional; `*` for mobile |

## Deploy errors (auto-fixed on startup)

`scripts/prepare_db.py` runs before the API on each deploy:

| Error | Fix applied automatically |
|-------|---------------------------|
| `DuplicateTable: clubs already exists` | Stamp base revision `82709d7f2519`, then `upgrade head` |
| `column users.apple_sub does not exist` | DB was wrongly stamped at head; rewind Alembic and run missing migrations |

Do **not** run `alembic stamp head` on a database that already has tables — that skips migrations.

Redeploy after pulling the latest `prepare_db.py`.

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
