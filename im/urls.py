#basic libraries
from django.urls import path

#import 
from im.views.category.views import categoryList, categoryCreate,categoryEdit,categoryDelete
from im.views.product.views import productList, productCreate,productEdit,productDelete
from im.views.audit_views import (
    audit_list, audit_start, audit_select_products, audit_enter_counts,
    audit_review, audit_apply_adjustments, audit_summary, audit_delete, audit_reports,
    audit_product_search, audit_join, audit_provider_count
)
from im.views.scan_views import audit_scan, audit_scan_lookup, audit_scan_save, audit_scan_finish
from im.views.import_products import import_products_csv_view
from im.views.despiece_views import despiece_list, despiece_process
from im.views.alarm_views import alarm_list, alarm_skip, alarm_skip_all, alarm_config, alarm_adjust, alarm_delete
from im.views.group_views import group_list, group_create, group_edit, group_delete, group_product_search, group_add_product, group_remove_product


app_name='im'
urlpatterns=[
        path('category/list',categoryList,name='categoryList'),
        path('category/create',categoryCreate,name='categoryCreate'),
        path('category/edit/<int:pk>/',categoryEdit, name='categoryEdit'),
        path('category/delete/<int:pk>/',categoryDelete,name='categoryDelete'),

        path('product/list',productList,name='productList'),
        path('product/create',productCreate,name='productCreate'),
        path('product/edit/<int:pk>/',productEdit, name='productEdit'),
        path('product/delete/<int:pk>/',productDelete,name='productDelete'),
        path('product/import-csv/', import_products_csv_view, name='import_products_csv'),

        # Audit URLs
        path('audit/', audit_list, name='audit_list'),
        path('audit/start/', audit_start, name='audit_start'),
        path('audit/reports/', audit_reports, name='audit_reports'),
        path('audit/<int:audit_id>/select/', audit_select_products, name='audit_select_products'),
        path('audit/<int:audit_id>/count/', audit_enter_counts, name='audit_enter_counts'),
        path('audit/<int:audit_id>/review/', audit_review, name='audit_review'),
        path('audit/<int:audit_id>/apply/', audit_apply_adjustments, name='audit_apply_adjustments'),
        path('audit/<int:audit_id>/summary/', audit_summary, name='audit_summary'),
        path('audit/<int:audit_id>/delete/', audit_delete, name='audit_delete'),
        path('audit/product-search/', audit_product_search, name='audit_product_search'),
        path('audit/scan/lookup/', audit_scan_lookup, name='audit_scan_lookup'),
        path('audit/<int:audit_id>/scan/', audit_scan, name='audit_scan'),
        path('audit/<int:audit_id>/scan/save/', audit_scan_save, name='audit_scan_save'),
        path('audit/<int:audit_id>/scan/finish/', audit_scan_finish, name='audit_scan_finish'),
        path('audit/<int:audit_id>/join/', audit_join, name='audit_join'),
        path('audit/<int:audit_id>/provider-count/', audit_provider_count, name='audit_provider_count'),

        # Despiece URLs
        path('product/despiece/', despiece_list, name='despiece_list'),
        path('product/despiece/<int:pk>/process/', despiece_process, name='despiece_process'),

        # Group URLs
        path('group/list', group_list, name='groupList'),
        path('group/create', group_create, name='groupCreate'),
        path('group/edit/<int:pk>/', group_edit, name='groupEdit'),
        path('group/delete/<int:pk>/', group_delete, name='groupDelete'),
        path('group/product-search/', group_product_search, name='groupProductSearch'),
        path('group/<int:pk>/add-product/', group_add_product, name='groupAddProduct'),
        path('group/<int:pk>/remove-product/<int:product_id>/', group_remove_product, name='groupRemoveProduct'),

        # Alarm URLs
        path('alarms/', alarm_list, name='alarm_list'),
        path('alarms/skip/<int:alarm_id>/', alarm_skip, name='alarm_skip'),
        path('alarms/skip-all/', alarm_skip_all, name='alarm_skip_all'),
        path('alarms/config/', alarm_config, name='alarm_config'),
        path('alarms/adjust/<int:alarm_id>/', alarm_adjust, name='alarm_adjust'),
        path('alarms/delete/<int:alarm_id>/', alarm_delete, name='alarm_delete'),
        ]
