from django.urls import path
from .views import select_business

urlpatterns = [
    path("select-business/", select_business, name="select_business"),
]
