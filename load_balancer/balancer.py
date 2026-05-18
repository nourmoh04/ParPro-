import itertools
import threading

SERVERS = [
    {"id": "server_1", "url": "http://127.0.0.1:8001"},
    {"id": "server_2", "url": "http://127.0.0.1:8002"},
    {"id": "server_3", "url": "http://127.0.0.1:8003"},
]

server_stats = {s["id"]: {"requests": 0, "active_connections": 0} for s in SERVERS}
stats_lock = threading.Lock()
_rr_cycle = itertools.cycle(SERVERS)
_rr_lock = threading.Lock()

def round_robin():
    with _rr_lock:
        return next(_rr_cycle)

def least_connections():
    with stats_lock:
        return min(SERVERS, key=lambda s: server_stats[s["id"]]["active_connections"])

def ip_hash(client_ip):
    return SERVERS[hash(client_ip) % len(SERVERS)]

def record_request(server_id):
    with stats_lock:
        server_stats[server_id]["requests"] += 1
        server_stats[server_id]["active_connections"] += 1

def release_connection(server_id):
    with stats_lock:
        if server_stats[server_id]["active_connections"] > 0:
            server_stats[server_id]["active_connections"] -= 1

def get_stats():
    with stats_lock:
        return dict(server_stats)


def reset_stats():
    with stats_lock:
        for server_id in server_stats:
            server_stats[server_id]["requests"] = 0
            server_stats[server_id]["active_connections"] = 0