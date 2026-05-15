# Deploy Stryde backend

## 1. Prepare production env vars

Copy `.env.example` to `.env` on the host (or set in Render/Railway dashboard). Required:

| Variable | Example |
|----------|---------|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/stryde` |
| `JWT_SECRET` | long random string |
| `RESET_TOKEN_SECRET` | long random string |
| `BACKEND_PUBLIC_URL` | `https://your-service.onrender.com` |
| `APPLE_CLIENT_ID` | `com.strydelabs.app` |
| `CORS_ALLOWED_ORIGINS` | `*` for mobile-only, or comma-separated origins |

Optional: AWS S3 keys for image uploads, SMTP, Stripe, Firebase path.

## 2. Deploy (Render + Docker)

1. Push `backend/` to GitHub (or connect this monorepo).
2. [Render](https://render.com) → **New → Web Service** → use `backend/render.yaml` or:
   - Root directory: `backend`
   - Runtime: **Docker**
   - Health check path: `/api/v1/health`
3. Add env vars from step 1 (`DATABASE_URL` from Render Postgres or external).
4. Deploy. Note the public URL, e.g. `https://stryde-api.onrender.com`.

## 3. Verify

```bash
curl https://YOUR_URL/api/v1/health
# {"status":"ok"}
```

## 4. Point the mobile app at the API

In `app/.env`:

```env
EXPO_PUBLIC_API_BASE_URL=https://YOUR_URL
```

Restart Expo (`npx expo start --clear`). All `apiFetch` / uploads / club WebSocket use this URL via `app/lib/config.ts`.

For EAS builds, set the same variable under `eas.json` → `build.production.env` or Expo dashboard **Environment variables**.

## 5. Rebuild the app after URL change

`EXPO_PUBLIC_*` values are embedded at build time. After changing the production URL, create a new EAS build or restart dev with `--clear`.
