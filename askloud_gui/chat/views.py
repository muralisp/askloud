"""
Django views for the Askloud chat GUI.

GET  /            → index.html (chat interface)
GET  /api/status/ → engine status (mode, resources, snapshot age)
POST /api/query/  → execute a query; returns structured JSON
POST /api/mode/   → switch snapshot/live mode
DELETE /api/history/ → clear conversation history for this session
"""

import json
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .engine_wrapper import EngineManager


def _mgr() -> EngineManager:
    return EngineManager.get()


def _session_id(request) -> str:
    """Return (creating if needed) a stable session key for this browser."""
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


# ── Pages ────────────────────────────────────────────────────────────────────

def index(request):
    return render(request, "chat/index.html")


# ── API ───────────────────────────────────────────────────────────────────────

@require_GET
def api_status(request):
    mgr = _mgr()
    return JsonResponse({
        "ready":         mgr.is_ready,
        "init_error":    mgr.init_error,
        "mode":          mgr.mode,
        "resources":     mgr.resource_types,
        "snapshot_age":  mgr.snapshot_age,
    })


@csrf_exempt
@require_POST
def api_query(request):
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    query = (body.get("query") or "").strip()
    if not query:
        return JsonResponse({"error": "query is required"}, status=400)

    # Allow the frontend to pass a tab-specific session ID so that Inventory
    # and Live tabs maintain independent conversation histories.
    client_sid = (body.get("session_id") or "").strip()
    mgr = _mgr()
    sid = client_sid if client_sid else _session_id(request)
    result = mgr.execute_query(sid, query)
    return JsonResponse(result)


@csrf_exempt
@require_POST
def api_mode(request):
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    mode   = (body.get("mode") or "").strip()
    mgr    = _mgr()
    active = mgr.switch_mode(mode)
    return JsonResponse({"mode": active})


@csrf_exempt
@require_POST
def api_reload(request):
    mgr    = _mgr()
    result = mgr.reload()
    return JsonResponse(result)


@csrf_exempt
def api_history(request):
    if request.method == "DELETE":
        client_sid = (request.GET.get("sid") or "").strip()
        mgr = _mgr()
        sid = client_sid if client_sid else _session_id(request)
        mgr.clear_history(sid)
        return JsonResponse({"cleared": True})
    return JsonResponse({"error": "Method not allowed"}, status=405)
