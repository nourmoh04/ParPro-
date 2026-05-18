from django.urls import path
from . import views

urlpatterns = [
    path('route/', views.route_request),
    path('stats/', views.get_server_stats),
]