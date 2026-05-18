import json
import requests as http_requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .balancer import (
    round_robin,
    least_connections,
    ip_hash,
    record_request,
    release_connection,
    get_stats,
    reset_stats,
)

@csrf_exempt
def route_request(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        body = json.loads(request.body)
        strategy = body.get("strategy", "round_robin")
        client_ip = request.META.get("REMOTE_ADDR", "127.0.0.1")
        target_path = body.get("path", "/orders/place-order/")

        if strategy == "round_robin":
            server = round_robin()
        elif strategy == "least_connections":
            server = least_connections()
        elif strategy == "ip_hash":
            server = ip_hash(client_ip)
        else:
            return JsonResponse({"error": "Unknown strategy"}, status=400)

        record_request(server["id"])
        target_url = f"{server['url']}{target_path}"

        try:
            forwarded = http_requests.post(target_url, json=body.get("payload", {}), timeout=10,proxies={"http": None, "https": None})
            server_response = forwarded.json()
            status = forwarded.status_code
        except http_requests.exceptions.ConnectionError:
            release_connection(server["id"])
            return JsonResponse({"error": f"{server['id']} is down"}, status=503)

        release_connection(server["id"])
        return JsonResponse({
            "success": True,
            "strategy": strategy,
            "routed_to": server["id"],
            "server_url": target_url,
            "server_response": server_response,
        }, status=status)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def get_server_stats(request):
    stats = get_stats()
    total = sum(s["requests"] for s in stats.values())
    return JsonResponse({
        "total_requests": total,
        "server_stats": stats,
        "distribution": {
            sid: f"{round(s['requests']/total*100)}%" if total > 0 else "0%"
            for sid, s in stats.items()
        },
    })

@csrf_exempt
def reset_server_stats(request):
    reset_stats()
    return JsonResponse({
        "success": True,
        "message": "Load balancer stats reset successfully"
    })