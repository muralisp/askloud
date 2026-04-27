# Askloud GUI — Django Framework Notes

## Django Framework — Concept & Workflow

Django is a Python web framework that follows the **MVT pattern** (Model-View-Template) and the principle of "batteries included."

---

## Core Components

| Component | What it is | In Askloud |
|---|---|---|
| **Model** | Defines data structure / DB schema | Not used (no DB — engine reads JSON files) |
| **View** | Business logic — handles request, returns response | `chat/views.py` |
| **Template** | HTML rendered server-side | `chat/templates/chat/index.html` |
| **URL conf** | Maps URL patterns to views | `askloud_gui/urls.py`, `chat/urls.py` |
| **Settings** | Central config (DB, apps, middleware…) | `askloud_gui/settings.py` |
| **App** | A self-contained module within the project | `chat/` is one app |

---

## Request/Response Lifecycle

```
Browser
  │
  │  GET /api/query/
  ▼
urls.py  ──────────────────────────────────────────
  │  urlpatterns matches the path
  │  calls the mapped view function
  ▼
views.py  ─────────────────────────────────────────
  │  receives HttpRequest object
  │  runs business logic
  │  (in Askloud: calls EngineManager.execute_query)
  │  returns HttpResponse / JsonResponse
  ▼
Middleware (on the way out)  ───────────────────────
  │  CSRF check, security headers, session save…
  ▼
Browser receives the response
```

---

## Project Structure

```
myproject/          ← project root (manage.py lives here)
  manage.py         ← CLI tool (runserver, migrate, shell…)
  myproject/        ← project package
    settings.py     ← global config
    urls.py         ← root URL router
    wsgi.py         ← WSGI entry point for production servers
  myapp/            ← one "app" (reusable module)
    models.py
    views.py
    urls.py
    templates/
    static/
    apps.py         ← AppConfig (lifecycle hooks like ready())
```

A **project** contains one or more **apps**. Apps are meant to be reusable — you could in theory plug the `chat` app into a different Django project.

---

## Key Concepts

**`AppConfig.ready()`**
Runs once when Django starts. Askloud uses this to initialize the engine:
```python
# chat/apps.py → ready() calls EngineManager.initialize()
```

**Middleware**
A stack of wrappers around every request/response. Order matters. Askloud uses `SessionMiddleware` (to maintain per-tab history) and `CsrfViewMiddleware` (CSRF token validation on POSTs).

**Static files**
CSS/JS served from `app/static/`. In `DEBUG=True`, Django serves them automatically via `django.contrib.staticfiles`. In production you'd run `collectstatic` and serve via nginx.

**Sessions**
Django tracks browser sessions via a cookie. Askloud stores conversation history keyed by `session.session_key` — that's why each browser tab gets its own history.

**`manage.py runserver`**
Single-threaded dev server. Fine for local use. For production you'd use gunicorn/uwsgi behind nginx.

---

## Askloud Request Flow

```
Browser sends POST /api/query/ {"query": "list EC2 instances"}
  │
  └─► urls.py routes to views.api_query()
        │
        └─► EngineManager.execute_query(session_id, query)
              │  (patches print_table, redirects stdout)
              └─► CloudInventoryEngine.process_query()
                    │  calls LLM → gets query plan → runs it
                    └─► print_table() → captured as structured JSON
              │
        returns {"items": [{type:"table",...}], "error": null}
        │
      JsonResponse(result) → back to browser
        │
      app.js routes tables → left panel, messages → right panel
```

Django itself only handles the HTTP layer — the heavy lifting (LLM calls, cloud API queries) happens inside `EngineManager`, which Django just calls like any other Python code.
