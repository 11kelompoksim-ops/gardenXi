from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("pembelian/", views.purchase_list, name="purchases"),
    path("pembelian/hapus/<int:pk>/", views.purchase_delete, name="purchase_delete"),

    path("stok-panen/", views.harvest_list, name="harvests"),
    path("stok-panen/hapus/<int:pk>/", views.harvest_delete, name="harvest_delete"),

    path("penjualan/", views.sale_list, name="sales"),
    path("penjualan/hapus/<int:pk>/", views.sale_delete, name="sale_delete"),

    path("retur/", views.return_list, name="returns"),
    path("retur/hapus/<int:pk>/", views.return_delete, name="return_delete"),

    path("journalling/", views.journal_list, name="journals"),
    path("journalling/hapus/<int:pk>/", views.journal_delete, name="journal_delete"),

    path("laporan/", views.report_view, name="report"),
]