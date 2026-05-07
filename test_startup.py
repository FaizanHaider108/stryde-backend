import sys
import os

print("Starting app import...")
sys.path.insert(0, os.getcwd())

# Import just the parts needed
from app.lib.db import Base, engine

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created!")

# Now import app and routers
print("Importing app...")
from app.main import app
print("App imported!")

print("\nTriggering startup...")
from app.main import on_startup
on_startup()
print("Startup complete!")

print(f"\nTotal routes: {len(app.routes)}")
plan_routes = [r for r in app.routes if 'plan' in str(getattr(r, 'path', '')).lower()]
print(f"Plan routes: {len(plan_routes)}")
for r in plan_routes:
    print(f"  - {r.path}")
