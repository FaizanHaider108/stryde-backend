import json
import time
import uvicorn

from app.main import app

_DEBUG_LOG_PATH = "debug-e6c601.log"


def _debug_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "e6c601",
            "runId": "post-fix",
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


_debug_log("H6", "backend/main.py:30", "module_loaded_with_app", {"has_app": app is not None})


def main():
    _debug_log("H7", "backend/main.py:34", "main_invoked_starting_uvicorn", {"host": "127.0.0.1", "port": 8000})
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
