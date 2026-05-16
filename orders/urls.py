from django.urls import path
from .views import place_order, place_order_unsafe

urlpatterns = [
    path("place-order/", place_order),
    path("place-order-unsafe/", place_order_unsafe),
]