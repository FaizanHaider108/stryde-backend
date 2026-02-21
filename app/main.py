from fastapi import FastAPI
from .lib.db import engine, Base
from .api.v1 import auth as auth_router

app = FastAPI(title="Stryde Backend")


def _create_tables():
	# Import models so they are registered on Base.metadata
	from .models import user  # noqa: F401

	Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def on_startup():
	_create_tables()
	app.include_router(auth_router.router)


@app.get("/")
def read_root():
	return {"status": "ok"}
