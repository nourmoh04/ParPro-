from django.urls import path
from .import views

urlpatterns = [
    path("place-order/", views.place_order),
    path("place-order-unsafe/",views. place_order_unsafe),
    path('place-order-sync/',   views.place_order_sync),
    path('place-order-async/',  views.place_order_async),
]