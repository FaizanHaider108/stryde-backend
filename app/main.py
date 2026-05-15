import logging
import os
import json
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uuid
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError
from fastapi.encoders import jsonable_encoder

from .api.v1 import auth as auth_router
from .api.v1 import profile as profile_router
from .api.v1 import club as club_router
from .api.v1 import event as event_router
from .api.v1 import route as route_router
from .api.v1 import run as run_router
from .api.v1 import race as race_router
from .api.v1 import post as post_router
from .api.v1 import chat as chat_router
from .api.v1 import notifications as notifications_router
from .api.v1 import upload as upload_router
from .api.v1 import plan as plan_router
from .api.v1.subscription import router as subscription_router
from .lib.db import Base, engine

logger = logging.getLogger(__name__)
uvicorn_logger = logging.getLogger("uvicorn.error")
_DEBUG_LOG_PATH = "debug-e6c601.log"


def _debug_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
	# region agent log
	try:
		payload = {
			"sessionId": "e6c601",
			"runId": "pre-fix",
			"hypothesisId": hypothesis_id,
			"location": location,
			"message": message,
			"data": data,
			"timestamp": int(time.time() * 1000),
		}
		with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as fp:
			fp.write(json.dumps(payload) + "\n")
	except Exception:
		pass
	# endregion

app = FastAPI(title="Stryde Backend", redirect_slashes=False)
_debug_log("H1", "app/main.py:51", "app_initialized", {"initial_routes": len(app.routes)})


def _register_routers() -> None:
	app.include_router(auth_router.router)
	app.include_router(profile_router.router)
	app.include_router(club_router.router)
	app.include_router(event_router.router)
	app.include_router(route_router.router)
	app.include_router(run_router.router)
	app.include_router(race_router.router)
	app.include_router(post_router.router)
	app.include_router(chat_router.router)
	app.include_router(notifications_router.router)
	app.include_router(upload_router.router)
	app.include_router(plan_router.router)
	app.include_router(subscription_router)
	_debug_log("H4", "app/main.py:66", "routers_registered_at_init", {"routes_after_register": len(app.routes)})


_register_routers()

def _load_cors_origins() -> list[str]:
	raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
	if raw:
		return [origin.strip() for origin in raw.split(",") if origin.strip()]
	return [
		"http://localhost:3000",
		"http://127.0.0.1:3000",
		"http://localhost:8081",
		"http://127.0.0.1:8081",
	]


origins = _load_cors_origins()

app.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.middleware("http")
async def request_trace_middleware(request: Request, call_next):
	request_id = str(uuid.uuid4())[:8]
	uvicorn_logger.info("[REQ %s] %s %s", request_id, request.method, request.url.path)
	response = await call_next(request)
	uvicorn_logger.info("[RES %s] %s %s -> %s", request_id, request.method, request.url.path, response.status_code)
	return response


_ERROR_MESSAGE_MAP = {
	"club not found": "The requested club could not be found.",
	"event not found": "The requested event could not be found.",
	"invitation not found": "The invitation could not be found.",
	"notification not found": "The notification could not be found.",
	"user not found": "The requested user could not be found.",
	"post not found": "The requested post could not be found.",
	"comment not found": "The requested comment could not be found.",
	"route not found": "The requested route could not be found.",
	"route not found or access denied": "Route not found, or you do not have access to it.",
	"run not found or access denied": "Run not found, or you do not have access to it.",
	"invalid or expired token": "The reset token is invalid or has expired.",
	"incorrect email or password": "The email or password you entered is incorrect.",
	"email already registered": "An account with this email already exists.",
	"could not create user": "We could not create your account at this time.",
	"limit must be positive": "The limit value must be greater than 0.",
	"invalid token payload": "Your session token is invalid. Please sign in again.",
	"missing credentials": "Authentication is required for this request.",
	"invalid token": "Your session token is invalid. Please sign in again.",
	"token expired": "Your session has expired. Please sign in again.",
	"only members can view members": "Only club members can view the member list.",
	"reset_password_url not configured": "Password reset is not configured on the server.",
}


def _humanize_error_detail(detail: str) -> str:
	message = detail.strip()
	if not message:
		return "The request could not be processed."

	mapped = _ERROR_MESSAGE_MAP.get(message.lower())
	if mapped:
		return mapped

	# Fallback: make existing message readable without changing the error mechanism.
	message = message[0].upper() + message[1:] if message else message
	if message[-1] not in ".!?":
		message += "."
	return message


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
	if isinstance(exc.detail, str):
		content = {"detail": _humanize_error_detail(exc.detail)}
	else:
		content = {"detail": exc.detail}
	return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
	error_messages = []
	for error in exc.errors():
		loc = [str(part) for part in error.get("loc", []) if part not in {"body", "query", "path", "header"}]
		field = ".".join(loc)
		msg = error.get("msg", "Invalid value")
		error_messages.append(f"{field}: {msg}" if field else str(msg))

	detail = "Invalid request data"
	if error_messages:
		detail = f"Invalid request data. {'; '.join(error_messages[:3])}."

	# Ensure nested ctx values (e.g. ValueError objects) are JSON-safe.
	safe_errors = jsonable_encoder(exc.errors(), custom_encoder={ValueError: lambda v: str(v)})

	return JSONResponse(
		status_code=422,
		content={
			"detail": detail,
			"errors": safe_errors,
		},
	)

def _create_tables() -> None:
	# Import models so they are registered on Base.metadata
	from .models import user, password_reset, chat, notification, plan, subscription  # noqa: F401
	Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def on_startup():
	_debug_log("H2", "app/main.py:157", "startup_enter", {"routes_before_startup": len(app.routes)})
	strict_startup = os.getenv("DB_STARTUP_STRICT", "false").lower() in {"1", "true", "yes", "on"}
	verbose_startup_errors = os.getenv("DB_STARTUP_VERBOSE_ERRORS", "false").lower() in {"1", "true", "yes", "on"}
	try:
		_create_tables()
	except SQLAlchemyError:
		if strict_startup:
			raise
		if verbose_startup_errors:
			logger.exception("Database initialization failed during startup.")
		else:
			logger.warning("Database initialization skipped: database is currently unreachable.")
		logger.warning(
			"API started without DB initialization (DB_STARTUP_STRICT is disabled)."
		)
		logger.info(
			"Tip: set DB_STARTUP_VERBOSE_ERRORS=true for full traceback, "
			"or DB_STARTUP_STRICT=true to fail startup."
		)

	_debug_log("H3", "app/main.py:191", "startup_completed_without_router_registration", {"routes_after_startup": len(app.routes)})


@app.get("/api/v1/health")
def read_root():
	return {"status": "ok"}


# Setup static file serving for uploads
upload_dir = Path("uploads")
upload_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")
