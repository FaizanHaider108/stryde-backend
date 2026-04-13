from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from .lib.db import Base, engine

app = FastAPI(title="Stryde Backend")

# CORS: allow local frontend during development
origins = [
	"*",
]

app.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

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

	return JSONResponse(
		status_code=422,
		content={
			"detail": detail,
			"errors": exc.errors(),
		},
	)

def _create_tables():
	# Import models so they are registered on Base.metadata
	from .models import user, password_reset, chat, notification  # noqa: F401

	Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def on_startup():
	_create_tables()
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


@app.get("/api/v1/health")
def read_root():
	return {"status": "ok"}
