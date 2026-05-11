from django.db import models, transaction
from django.utils import timezone
from django.db.models.signals import post_save,post_delete
from django.dispatch import receiver
from im.models import Product
from django.db.models.functions import Lower
from decimal import Decimal

class Provider(models.Model):
    #Basic Files
    id = models.CharField(primary_key=True,max_length=50,verbose_name='id')
    name = models.CharField(max_length=150, verbose_name='Name',unique=True)
    address = models.CharField(max_length=150, null=True, blank=True, verbose_name='Address')
    phoneNumber = models.CharField(max_length=150, verbose_name='Phone')
    #utility fields
    date_created = models.DateTimeField(blank=True, null=True)
    last_updated = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return '{}'.format(self.name)

    def save(self, *args, **kwargs):
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())
        super (Provider, self).save(*args,**kwargs)

    class Meta:
        verbose_name = 'Provider'
        verbose_name_plural = 'Providers'
        ordering=[Lower('name')]

class Purchase(models.Model):
    #basic fields
    id=models.AutoField(primary_key=True,verbose_name='id')
    providerid= models.CharField(max_length=100,default='na')

    #foreing fields
    provider= models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True,default='mostrador')

    #utility fields
    date_created= models.DateTimeField(blank=True, null=True)
    last_update = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return '{}'.format(self.id)

    def save    (self,*args,**kwargs):
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())
        super (Purchase,self).save(*args,**kwargs)

    class Meta:
        verbose_name='purchase'
        verbose_name_plural='purchases'
        ordering = ['-id']

    @property
    def get_cart_total(self):
        orderitems=self.purchaseitem_set.all()
        total= sum([item.get_total for item in orderitems])
        return total

class purchaseItem(models.Model):
    product= models.ForeignKey('im.Product', on_delete=models.SET_NULL, null=True,blank=True)
    purchase= models.ForeignKey(Purchase, on_delete=models.CASCADE)
    quantity=models.IntegerField(default=0,null=True,blank=True)
    cost=models.CharField(max_length=1000,verbose_name='cost',default=0)

    #utility fields
    date_created = models.DateTimeField(blank=True, null=True)
    last_update = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return '{} {}'.format(self.id, self.purchase)


    def save    (self,*args,**kwargs):
        if self.date_created is None:
            self.date_created = timezone.localtime(timezone.now())
        self.last_updated = timezone.localtime(timezone.now())
        super (purchaseItem,self).save(*args,**kwargs)

    class Meta:
        verbose_name='purchaseItem'
        verbose_name_plural='purchasesItems'
        ordering = ['-id']

    @property
    def get_total(self):
        total=float(self.cost)*float(self.quantity)
        return total

@receiver(post_save, sender=purchaseItem)
def purchase_item_post_save(sender, instance, **kwargs):
    """Update ProductProvider cost when purchase item is received"""
    if instance.product and instance.purchase.provider and instance.cost:
        from decimal import Decimal
        from im.models import ProductProvider
        
        # Convert cost to Decimal
        cost = Decimal(str(instance.cost))
        
        # Get or create ProductProvider pair
        pp, created = ProductProvider.objects.get_or_create(
            product=instance.product,
            provider=instance.purchase.provider
        )
        
        # Update the provider cost with the received cost
        pp.provider_cost = cost
        pp.save()  # This will call update_average_cost() in ProductProvider.save()



@receiver(post_delete, sender=purchaseItem)
def purchase_item_post_delete(sender, instance, **kwargs):
    # Disabled: Stock is now tracked via InventoryUnit status, not updated here
    # Inventory availability is calculated dynamically via Product.stock_ready_to_sale
    pass


# Purchase Order Workflow Models (Phase 3)

class PurchaseOrder(models.Model):
    """
    Represents a purchase order with multi-stage workflow.
    Statuses: draft -> approved -> sent -> received -> completed
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('sent', 'Sent to Supplier'),
        ('received', 'Received'),
        ('completed', 'Completed'),
    ]

    po_number = models.CharField(max_length=50, unique=True, verbose_name='PO Number')
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, verbose_name='Supplier')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='Status')
    
    # Order info
    created_by = models.CharField(max_length=150, null=True, blank=True, verbose_name='Created By')
    approved_by = models.CharField(max_length=150, null=True, blank=True, verbose_name='Approved By')
    received_by = models.CharField(max_length=150, null=True, blank=True, verbose_name='Received By')
    completed_by = models.CharField(max_length=150, null=True, blank=True, verbose_name='Completed By')
    
    # Tracking info
    order_type = models.CharField(
        max_length=20,
        choices=[('instant', 'Instant Purchase'), ('auto_forecast', 'Auto from Forecast'), ('manual_stock', 'Manual from Min/Max')],
        default='manual_stock',
        verbose_name='Order Type'
    )
    creation_method = models.CharField(
        max_length=20,
        choices=[('auto_forecast', 'Auto from Forecast'), ('manual_stock', 'Manual from Min/Max')],
        default='manual_stock',
        verbose_name='Creation Method'
    )
    tracking_reference = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name='Supplier Tracking Reference'
    )
    
    # Dates
    created_date = models.DateTimeField(auto_now_add=True, verbose_name='Created Date')
    approved_date = models.DateTimeField(null=True, blank=True, verbose_name='Approved Date')
    sent_date = models.DateTimeField(null=True, blank=True, verbose_name='Sent Date')
    received_date = models.DateTimeField(null=True, blank=True, verbose_name='Received Date')
    completed_date = models.DateTimeField(null=True, blank=True, verbose_name='Completed Date')
    
    # Totals (calculated)
    total_items = models.IntegerField(default=0, verbose_name='Total Items')
    total_ordered_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Total Ordered Cost'
    )
    total_received_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Total Received Cost'
    )
    
    class Meta:
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'
        ordering = ['-created_date']
    
    def __str__(self):
        return f"PO {self.po_number} ({self.status}) - {self.provider.name}"


class PurchaseOrderItem(models.Model):
    """Represents individual items in a purchase order"""
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items', verbose_name='Purchase Order')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Product')
    
    # Quantities
    ordered_quantity = models.IntegerField(verbose_name='Ordered Quantity')
    received_quantity = models.IntegerField(default=0, verbose_name='Received Quantity')
    
    # Costs
    ordered_cost_per_unit = models.DecimalField(
        max_digits=10, decimal_places=6, verbose_name='Ordered Cost per Unit'
    )
    received_cost_per_unit = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True, verbose_name='Received Cost per Unit'
    )
    
    # Totals
    ordered_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Ordered Total'
    )
    received_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name='Received Total'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated At')
    
    class Meta:
        verbose_name = 'Purchase Order Item'
        verbose_name_plural = 'Purchase Order Items'
        unique_together = ('purchase_order', 'product')
    
    def __str__(self):
        return f"{self.purchase_order.po_number} - {self.product.name}"
    
    def save(self, *args, **kwargs):
        # Calculate totals
        self.ordered_total = self.ordered_quantity * self.ordered_cost_per_unit
        if self.received_cost_per_unit and self.received_quantity > 0:
            self.received_total = self.received_quantity * self.received_cost_per_unit
        else:
            self.received_total = Decimal('0')
        super().save(*args, **kwargs)


class OrderLog(models.Model):
    """Audit trail for all changes to purchase orders"""
    LOG_ACTIONS = [
        ('created', 'Order Created'),
        ('quantity_changed', 'Quantity Changed'),
        ('cost_changed', 'Cost Changed'),
        ('approved', 'Order Approved'),
        ('sent', 'Order Sent'),
        ('received', 'Order Received'),
        ('received_qty_changed', 'Received Quantity Changed'),
        ('received_cost_changed', 'Received Cost Changed'),
        ('completed', 'Order Completed'),
        ('status_changed', 'Status Changed'),
    ]
    
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='logs', verbose_name='Purchase Order')
    po_item = models.ForeignKey(PurchaseOrderItem, on_delete=models.CASCADE, null=True, blank=True, verbose_name='PO Item')
    
    action = models.CharField(max_length=30, choices=LOG_ACTIONS, verbose_name='Action')
    performed_by = models.CharField(max_length=150, verbose_name='Performed By')
    
    # Change tracking
    field_name = models.CharField(max_length=50, null=True, blank=True, verbose_name='Field Changed')
    old_value = models.TextField(null=True, blank=True, verbose_name='Old Value')
    new_value = models.TextField(null=True, blank=True, verbose_name='New Value')
    
    notes = models.TextField(null=True, blank=True, verbose_name='Notes')
    
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='Timestamp')
    
    class Meta:
        verbose_name = 'Order Log'
        verbose_name_plural = 'Order Logs'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.purchase_order.po_number} - {self.get_action_display()} - {self.timestamp}"


# Signal Handlers for PurchaseOrder workflow

@receiver(post_save, sender=PurchaseOrderItem)
def update_po_totals_on_item_change(sender, instance, created, **kwargs):
    """Recalculate PO totals when an item is created/updated"""
    po = instance.purchase_order
    total_items = 0
    total_ordered_cost = Decimal('0')
    total_received_cost = Decimal('0')
    
    for item in po.items.all():
        total_items += item.ordered_quantity
        total_ordered_cost += item.ordered_total
        if item.received_quantity > 0:
            total_received_cost += item.received_total
    
    with transaction.atomic():
        po.total_items = total_items
        po.total_ordered_cost = total_ordered_cost
        po.total_received_cost = total_received_cost
        po.save()


@receiver(post_save, sender=PurchaseOrderItem)
def update_provider_cost_on_po_item_received(sender, instance, created, **kwargs):
    """Update ProductProvider cost when PO item is received with actual cost"""
    # Only update when received_cost_per_unit is set (indicating actual receipt)
    if instance.product and instance.purchase_order.provider and instance.received_cost_per_unit and instance.received_quantity > 0:
        from im.models import ProductProvider
        
        # Get or create ProductProvider pair
        pp, created_pp = ProductProvider.objects.get_or_create(
            product=instance.product,
            provider=instance.purchase_order.provider
        )
        
        # Update the provider cost with the received cost
        pp.provider_cost = instance.received_cost_per_unit
        pp.save()  # This will call update_average_cost() in ProductProvider.save()
