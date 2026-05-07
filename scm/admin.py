from django.contrib import admin
from scm.models import Provider, Purchase, purchaseItem, PurchaseOrder, PurchaseOrderItem, OrderLog
from im.models import Product
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from django.shortcuts import render, redirect
from django.urls import path
from django.http import HttpResponseRedirect
from django.contrib import messages

class providerResource(resources.ModelResource):
    class Meta:
        model = Provider

class providerAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    search_fields=('id','name')
    list_filter=()
    resource_class=providerResource
    actions = ['create_bulk_order']
    
    def create_bulk_order(self, request, queryset):
        """Action to create bulk purchase orders"""
        if 'apply' in request.POST:
            # User confirmed the action - process the form
            provider_id = request.POST.get('provider_id')
            if not provider_id:
                self.message_user(request, 'Please select a provider', level='error')
                return
            
            provider = Provider.objects.get(id=provider_id)
            
            # Create the purchase order
            purchase = Purchase.objects.create(provider=provider)
            
            # Process product items
            products = Product.objects.filter(active=True)
            items_created = 0
            
            for product in products:
                quantity_key = f'qty_{product.id}'
                if quantity_key in request.POST:
                    qty = request.POST.get(quantity_key, '0').strip()
                    if qty and int(qty) > 0:
                        purchaseItem.objects.create(
                            product=product,
                            purchase=purchase,
                            quantity=int(qty),
                            cost=str(product.costo)
                        )
                        items_created += 1
            
            if items_created > 0:
                self.message_user(
                    request,
                    f'✓ Purchase order #{purchase.id} created with {items_created} items from {provider.name}',
                    level='success'
                )
                return redirect('admin:scm_purchase_change', purchase.id)
            else:
                purchase.delete()
                self.message_user(request, 'No items were added to the order', level='warning')
                return
        
        # Show the form for bulk order creation
        return render(request, 'admin/scm/provider/bulk_order_form.html', {
            'providers': Provider.objects.all(),
            'products': Product.objects.filter(active=True),
            'action': 'create_bulk_order',
        })
    
    create_bulk_order.short_description = 'Create purchase order for selected provider'

admin.site.register(Provider, providerAdmin)

class purchaseResource(resources.ModelResource):
    class Meta:
        model = Purchase
        

class purchaseAdmin(ImportExportModelAdmin,admin.ModelAdmin):
    search_fields=('id',)
    list_filter=('provider',)
    resource_class=purchaseResource
    list_display=('id','provider','date_created')
    ordering=('date_created',)
    date_hierarchy='date_created'

admin.site.register(Purchase,purchaseAdmin)

class purchaseItemResource(resources.ModelResource):
    class Meta:
        model = purchaseItem

class purchaseItemAdmin(ImportExportModelAdmin,admin.ModelAdmin):
    search_fields=('id',)
    list_filter=('purchase',)
    resource_class=purchaseItemResource
    list_display=('id',)

admin.site.register(purchaseItem,purchaseItemAdmin)


# Purchase Order Workflow Admin

class OrderLogInline(admin.TabularInline):
    """Inline display of order logs"""
    model = OrderLog
    extra = 0
    readonly_fields = ('action', 'performed_by', 'field_name', 'old_value', 'new_value', 'notes', 'timestamp')
    can_delete = False
    fields = ('timestamp', 'action', 'performed_by', 'field_name', 'old_value', 'new_value', 'notes')


class PurchaseOrderItemInline(admin.TabularInline):
    """Inline editing of PO items"""
    model = PurchaseOrderItem
    extra = 1
    fields = ('product', 'ordered_quantity', 'ordered_cost_per_unit', 'ordered_total', 
              'received_quantity', 'received_cost_per_unit', 'received_total')
    
    def get_readonly_fields(self, request, obj=None):
        """Make fields read-only based on PO status"""
        if obj and obj.status in ['approved', 'sent', 'received', 'completed']:
            # Can edit quantities/costs in received status
            if obj.status == 'received':
                return ('product', 'ordered_quantity', 'ordered_cost_per_unit', 'ordered_total')
            else:
                # Read-only in all other non-draft statuses
                return ('product', 'ordered_quantity', 'ordered_cost_per_unit', 'ordered_total',
                        'received_quantity', 'received_cost_per_unit', 'received_total')
        return ('ordered_total', 'received_total')


class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'provider', 'status', 'total_items', 'total_ordered_cost', 'created_date')
    list_filter = ('status', 'provider', 'created_date', 'creation_method')
    search_fields = ('po_number', 'provider__name')
    readonly_fields = ('po_number', 'creation_method', 'created_date', 'approved_date', 'sent_date', 
                       'received_date', 'completed_date', 'total_items', 'total_ordered_cost', 'total_received_cost')
    
    fieldsets = (
        ('Order Info', {
            'fields': ('po_number', 'provider', 'status', 'creation_method')
        }),
        ('Dates', {
            'fields': ('created_date', 'approved_date', 'sent_date', 'received_date', 'completed_date')
        }),
        ('Users', {
            'fields': ('created_by', 'approved_by', 'received_by', 'completed_by')
        }),
        ('Tracking', {
            'fields': ('tracking_reference',)
        }),
        ('Totals', {
            'fields': ('total_items', 'total_ordered_cost', 'total_received_cost'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [PurchaseOrderItemInline, OrderLogInline]
    actions = ['approve_action', 'send_action', 'receive_action', 'complete_action']
    
    def get_readonly_fields(self, request, obj=None):
        """Adjust readonly fields based on status"""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj:
            if obj.status != 'draft':
                readonly.extend(['created_by'])
            if obj.status in ['approved', 'sent', 'received', 'completed']:
                readonly.extend(['provider'])
        return readonly
    
    def approve_action(self, request, queryset):
        """Approve selected draft orders"""
        from scm.po_operations import approve_purchase_order
        count = 0
        for po in queryset.filter(status='draft'):
            try:
                approve_purchase_order(po, approved_by=str(request.user))
                count += 1
            except ValueError as e:
                self.message_user(request, f"Error approving {po.po_number}: {e}", level='error')
        self.message_user(request, f"✓ {count} orders approved", level='success')
    approve_action.short_description = "Approve selected orders"
    
    def send_action(self, request, queryset):
        """Send selected approved orders"""
        from scm.po_operations import send_purchase_order
        count = 0
        for po in queryset.filter(status='approved'):
            try:
                send_purchase_order(po, sent_by=str(request.user))
                count += 1
            except ValueError as e:
                self.message_user(request, f"Error sending {po.po_number}: {e}", level='error')
        self.message_user(request, f"✓ {count} orders sent", level='success')
    send_action.short_description = "Send selected orders to suppliers"
    
    def receive_action(self, request, queryset):
        """Receive selected sent orders"""
        from scm.po_operations import receive_purchase_order
        count = 0
        for po in queryset.filter(status='sent'):
            try:
                receive_purchase_order(po, received_by=str(request.user))
                count += 1
            except ValueError as e:
                self.message_user(request, f"Error receiving {po.po_number}: {e}", level='error')
        self.message_user(request, f"✓ {count} orders marked as received", level='success')
    receive_action.short_description = "Mark orders as received"
    
    def complete_action(self, request, queryset):
        """Complete selected received orders"""
        from scm.po_operations import complete_purchase_order
        count = 0
        for po in queryset.filter(status='received'):
            try:
                complete_purchase_order(po, completed_by=str(request.user))
                count += 1
            except ValueError as e:
                self.message_user(request, f"Error completing {po.po_number}: {e}", level='error')
        self.message_user(request, f"✓ {count} orders completed and converted to purchases", level='success')
    complete_action.short_description = "Complete received orders (create purchases)"


class OrderLogAdmin(admin.ModelAdmin):
    list_display = ('purchase_order', 'action', 'performed_by', 'timestamp')
    list_filter = ('action', 'performed_by', 'timestamp')
    search_fields = ('purchase_order__po_number', 'performed_by')
    readonly_fields = ('purchase_order', 'po_item', 'action', 'performed_by', 'field_name', 
                       'old_value', 'new_value', 'notes', 'timestamp')
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(PurchaseOrder, PurchaseOrderAdmin)
admin.site.register(OrderLog, OrderLogAdmin)

