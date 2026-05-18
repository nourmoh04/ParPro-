import queue
import threading
import time
import uuid
from datetime import datetime


task_queue = queue.Queue()

task_logs = {}
task_logs_lock = threading.Lock()

worker_started = False
worker_lock = threading.Lock()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _set_task_status(task_id, status, message=""):
    with task_logs_lock:
        if task_id not in task_logs:
            task_logs[task_id] = {}

        task_logs[task_id].update({
            "status": status,
            "message": message,
            "updated_at": _now(),
        })


def enqueue_task(task_name, func, *args, **kwargs):
    ensure_worker_started()

    task_id = str(uuid.uuid4())

    with task_logs_lock:
        task_logs[task_id] = {
            "task_id": task_id,
            "task_name": task_name,
            "status": "queued",
            "message": "Task added to queue",
            "created_at": _now(),
            "updated_at": _now(),
        }

    task_queue.put({
        "task_id": task_id,
        "task_name": task_name,
        "func": func,
        "args": args,
        "kwargs": kwargs,
    })

    return task_id


def worker():
    print("[ASYNC QUEUE] Worker started and waiting for tasks...")

    while True:
        task = task_queue.get()

        task_id = task["task_id"]
        task_name = task["task_name"]
        func = task["func"]
        args = task["args"]
        kwargs = task["kwargs"]

        try:
            _set_task_status(
                task_id,
                "running",
                f"Task {task_name} is running"
            )

            start_time = time.time()

            func(*args, **kwargs)

            duration = round(time.time() - start_time, 3)

            _set_task_status(
                task_id,
                "completed",
                f"Task {task_name} completed in {duration}s"
            )

        except Exception as exc:
            _set_task_status(
                task_id,
                "failed",
                f"Task {task_name} failed: {exc}"
            )

        finally:
            task_queue.task_done()


def ensure_worker_started():
    global worker_started

    with worker_lock:
        if not worker_started:
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            worker_started = True


def get_queue_status():
    with task_logs_lock:
        logs_snapshot = list(task_logs.values())

    return {
        "queued_tasks": task_queue.qsize(),
        "worker_started": worker_started,
        "total_logged_tasks": len(logs_snapshot),
        "tasks": logs_snapshot[-20:],
    }