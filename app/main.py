from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import auth as auth_router
from .api.v1 import profile as profile_router
from .lib.db import Base, engine

app = FastAPI(title="Stryde Backend")

# CORS: allow local frontend during development
origins = [
	"http://localhost:3000",
	"http://127.0.0.1:3000",
]

app.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

def _create_tables():
	# Import models so they are registered on Base.metadata
	from .models import user  # noqa: F401

	Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def on_startup():
	_create_tables()
	app.include_router(auth_router.router)
	app.include_router(profile_router.router)


@app.get("/")
def read_root():
	return {"status": "ok"}
