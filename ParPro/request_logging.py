import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone


_log_lock = threading.Lock()


class StructuredRequestLoggingMiddleware:
    """
    Structured request logging middleware.

    It writes one JSON object per HTTP request to logs/request_logs.jsonl.
    This is used for Req #10 benchmarking and bottleneck analysis.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.log_dir = "logs"
        self.log_file = os.path.join(self.log_dir, "request_logs.jsonl")
        os.makedirs(self.log_dir, exist_ok=True)

    def __call__(self, request):
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        response = self.get_response(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 3)

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "is_error": response.status_code >= 400,
        }

        with _log_lock:
            with open(self.log_file, "a", encoding="utf-8") as file:
                file.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return response