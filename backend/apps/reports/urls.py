from django.urls import path

from . import views

urlpatterns = [
    path("reports/dashboard/", views.DashboardView.as_view(), name="reports-dashboard"),
    path("reports/export/<str:dataset>.csv", views.ExportView.as_view(), name="reports-export"),
]
