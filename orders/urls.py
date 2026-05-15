from django.urls import path
from . views import place_order

urlpatterns = [
        path('place-order/', place_order),

]