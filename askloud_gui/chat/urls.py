from django.urls import path
from . import views

urlpatterns = [
    path("",                 views.index,        name="index"),
    path("api/status/",      views.api_status,   name="api_status"),
    path("api/query/",       views.api_query,    name="api_query"),
    path("api/mode/",        views.api_mode,     name="api_mode"),
    path("api/history/",     views.api_history,  name="api_history"),
    path("api/reload/",      views.api_reload,   name="api_reload"),
]
