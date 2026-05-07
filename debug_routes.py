from app.main import app, on_startup
import asyncio

# Manually call startup function
on_startup()

print('\n=== ALL ROUTES ===')
for i, route in enumerate(app.routes):
    if hasattr(route, 'path'):
        methods = str(getattr(route, 'methods', 'N/A'))
        path = route.path
        if 'api/v1' in path or 'plan' in path.lower():
            print(f'{i}: {methods:<30} {path}')
