"""
Purchase Order workflow operations and utilities
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.db.models.signals import post_save
from .models import PurchaseOrder, PurchaseOrderItem, OrderLog, Purchase, purchaseItem
from im.models import Product, InventoryUnit, DemandForecast


def create_po_number():
    """Generate unique PO number"""
    from datetime import datetime
    import uuid
    # Format: PO-YYYYMMDD-XXXX (date + 4-digit random)
    date_part = datetime.now().strftime('%Y%m%d')
    random_part = uuid.uuid4().hex[:4].upper()
    po_number = f"PO-{date_part}-{random_part}"
    
    # Ensure uniqueness
    while PurchaseOrder.objects.filter(po_number=po_number).exists():
        random_part = uuid.uuid4().hex[:4].upper()
        po_number = f"PO-{date_part}-{random_part}"
    
    return po_number


def create_po_from_forecast(provider, created_by='system'):
    """
    Create a purchase order automatically from demand forecasts.
    Uses demand forecast data to suggest quantities.
    """
    # Get all products with active forecasts
    forecasts = DemandForecast.objects.filter(
        status='active',
        product__provider=provider
    ).select_related('product')
    
    if not forecasts.exists():
        raise ValueError(f"No active forecasts found for provider {provider.name}")
    
    with transaction.atomic():
        po = PurchaseOrder.objects.create(
            po_number=create_po_number(),
            provider=provider,
            status='draft',
            created_by=created_by,
            creation_method='auto_forecast'
        )
        
        total_items = 0
        total_cost = Decimal('0')
        
        for forecast in forecasts:
            product = forecast.product
            
            # Use EOQ from forecast for order quantity
            quantity = int(forecast.reorder_quantity) if forecast.reorder_quantity else 10
            
            # Get current product cost
            cost_per_unit = Decimal(str(product.costo)) if product.costo else Decimal('0')
            
            # Create PO item
            po_item = PurchaseOrderItem.objects.create(
                purchase_order=po,
                product=product,
                ordered_quantity=quantity,
                ordered_cost_per_unit=cost_per_unit
            )
            
            total_items += quantity
            total_cost += po_item.ordered_total
            
            # Log creation
            OrderLog.objects.create(
                purchase_order=po,
                po_item=po_item,
                action='created',
                performed_by=created_by,
                notes=f'Auto-created from forecast. ROP: {forecast.reorder_point}, EOQ: {forecast.reorder_quantity}'
            )
        
        # Update PO totals
        po.total_items = total_items
        po.total_ordered_cost = total_cost
        po.save()
        
        # Log PO creation
        OrderLog.objects.create(
            purchase_order=po,
            action='created',
            performed_by=created_by,
            notes=f'Auto-created from forecasts with {len(forecasts)} products'
        )
        
        return po


def create_po_from_manual(provider, items_data, created_by='system'):
    """
    Create a purchase order manually with operator-provided quantities.
    
    items_data: list of dicts with {'product_id': X, 'quantity': Y, 'cost_per_unit': Z}
    """
    if not items_data:
        raise ValueError("items_data cannot be empty")
    
    with transaction.atomic():
        po = PurchaseOrder.objects.create(
            po_number=create_po_number(),
            provider=provider,
            status='draft',
            created_by=created_by,
            creation_method='manual_stock'
        )
        
        total_items = 0
        total_cost = Decimal('0')
        
        for item_data in items_data:
            product = Product.objects.get(id=item_data['product_id'])
            quantity = int(item_data['quantity'])
            cost_per_unit = Decimal(str(item_data.get('cost_per_unit', product.costo or 0)))
            
            # Create PO item
            po_item = PurchaseOrderItem.objects.create(
                purchase_order=po,
                product=product,
                ordered_quantity=quantity,
                ordered_cost_per_unit=cost_per_unit
            )
            
            total_items += quantity
            total_cost += po_item.ordered_total
            
            # Log creation
            OrderLog.objects.create(
                purchase_order=po,
                po_item=po_item,
                action='created',
                performed_by=created_by
            )
        
        # Update PO totals
        po.total_items = total_items
        po.total_ordered_cost = total_cost
        po.save()
        
        # Log PO creation
        OrderLog.objects.create(
            purchase_order=po,
            action='created',
            performed_by=created_by,
            notes=f'Manually created with {len(items_data)} products'
        )
        
        return po


def approve_purchase_order(po, approved_by='system'):
    """Approve a purchase order (draft -> approved) and create initial inventory units"""
    if po.status != 'draft':
        raise ValueError(f"Cannot approve PO with status '{po.status}'. Only draft orders can be approved.")
    
    with transaction.atomic():
        po.status = 'approved'
        po.approved_by = approved_by
        po.approved_date = timezone.now()
        po.save()
        
        # Create inventory units with 'ordered' status
        create_inventory_units_for_po(po, approved_by)
        
        OrderLog.objects.create(
            purchase_order=po,
            action='approved',
            performed_by=approved_by,
            field_name='status',
            old_value='draft',
            new_value='approved'
        )


def send_purchase_order(po, tracking_reference=None, sent_by='system'):
    """Send a purchase order to supplier (approved -> sent) and update inventory units status"""
    if po.status != 'approved':
        raise ValueError(f"Cannot send PO with status '{po.status}'. Only approved orders can be sent.")
    
    with transaction.atomic():
        po.status = 'sent'
        po.sent_date = timezone.now()
        if tracking_reference:
            po.tracking_reference = tracking_reference
        po.save()
        
        # Update all inventory units to 'send' status
        update_inventory_units_status(po, 'send', sent_by)
        
        OrderLog.objects.create(
            purchase_order=po,
            action='sent',
            performed_by=sent_by,
            notes=f'Tracking reference: {tracking_reference}' if tracking_reference else None
        )


def create_inventory_units_for_po(po, created_by='system'):
    """
    Create individual InventoryUnit records for each item in the PO.
    Called when PO is approved - units start with 'ordered' status.
    """
    if not po.items.exists():
        return
    
    with transaction.atomic():
        units_created = 0
        for po_item in po.items.all():
            quantity = po_item.ordered_quantity
            
            for i in range(quantity):
                # Generate tracking ID: {po_id}-{item_index}
                tracking_id = f"{po.id}-{units_created + 1}"
                
                unit = InventoryUnit.objects.create(
                    tracking_id=tracking_id,
                    product=po_item.product,
                    purchase_order=po,
                    status='ordered',
                    purchase_cost=po_item.ordered_cost_per_unit,
                    ordered_date=timezone.now()
                )
                units_created += 1
        
        OrderLog.objects.create(
            purchase_order=po,
            action='inventory_units_created',
            performed_by=created_by,
            notes=f'Created {units_created} inventory units with tracking IDs'
        )


def update_inventory_units_status(po, new_status, updated_by='system'):
    """
    Update the status of all InventoryUnits for a PO.
    Called when PO transitions through workflow stages.
    """
    units = InventoryUnit.objects.filter(purchase_order=po)
    
    with transaction.atomic():
        for unit in units:
            unit.status = new_status
            
            # Set date fields based on status
            if new_status == 'send':
                pass  # No specific date field for 'send'
            elif new_status == 'received':
                unit.received_date = timezone.now()
                # Update received_cost from the PO item if it was modified
                po_item = unit.purchase_order.items.filter(product=unit.product).first()
                if po_item and po_item.received_cost_per_unit:
                    unit.received_cost = po_item.received_cost_per_unit
            elif new_status == 'ready_to_sale':
                unit.ready_date = timezone.now()
            
            unit.save()
        
        OrderLog.objects.create(
            purchase_order=po,
            action='inventory_units_updated',
            performed_by=updated_by,
            notes=f'Updated {units.count()} inventory units to status: {new_status}'
        )


def receive_purchase_order(po, received_by='system'):
    """Receive a purchase order (sent -> received) and update inventory units status"""
    if po.status != 'sent':
        raise ValueError(f"Cannot receive PO with status '{po.status}'. Only sent orders can be received.")
    
    with transaction.atomic():
        po.status = 'received'
        po.received_by = received_by
        po.received_date = timezone.now()
        po.save()
        
        # Update all inventory units to 'received' status
        update_inventory_units_status(po, 'received', received_by)
        
        OrderLog.objects.create(
            purchase_order=po,
            action='received',
            performed_by=received_by,
            notes='Purchase order marked as received'
        )


def complete_purchase_order(po, completed_by='system'):
    """
    Complete a purchase order (received -> completed).
    Creates Purchase and purchaseItems linked to existing InventoryUnits, then marks all as ready_to_sale.
    Disables the purchaseItem signal to prevent duplicate unit creation.
    Returns the created Purchase object.
    """
    if po.status != 'received':
        raise ValueError(f"Cannot complete PO with status '{po.status}'. Only received orders can be completed.")
    
    from im.signals import purchase_item_post_save
    
    with transaction.atomic():
        # Create Purchase record
        purchase = Purchase.objects.create(
            provider=po.provider,
            providerid=po.provider_id
        )
        
        # Disable signal to prevent duplicate unit creation
        post_save.disconnect(purchase_item_post_save, sender=purchaseItem)
        
        try:
            # Create purchaseItems for each PO item, linked to existing inventory units
            for po_item in po.items.all():
                quantity = po_item.received_quantity or po_item.ordered_quantity
                cost_per_unit = po_item.received_cost_per_unit or po_item.ordered_cost_per_unit
                
                # Create purchaseItem - signal is disabled, so no new units created
                purchase_item_obj = purchaseItem.objects.create(
                    purchase=purchase,
                    product=po_item.product,
                    quantity=quantity,
                    cost=str(cost_per_unit)  # purchaseItem uses cost as CharField
                )
                
                # Link existing inventory units to this purchaseItem
                # Get units for this product that don't yet have a purchase_item
                units_to_link = InventoryUnit.objects.filter(
                    product=po_item.product,
                    purchase_order=po,
                    purchase_item__isnull=True
                )[:quantity]
                
                for unit in units_to_link:
                    unit.purchase_item = purchase_item_obj
                    unit.received_cost = cost_per_unit
                    unit.save(update_fields=['purchase_item', 'received_cost'])
                
                # Update product cost if received_cost differs from ordered_cost
                ordered_cost = po_item.ordered_cost_per_unit
                received_cost = po_item.received_cost_per_unit
                if received_cost and ordered_cost and Decimal(str(received_cost)) != Decimal(str(ordered_cost)):
                    # Update product cost to the new received cost
                    po_item.product.costo = Decimal(str(received_cost))
                    po_item.product.save(update_fields=['costo', 'last_updated'])
                    
                    OrderLog.objects.create(
                        purchase_order=po,
                        po_item=po_item,
                        action='cost_updated',
                        performed_by=completed_by,
                        notes=f'Product cost updated from {ordered_cost} to {received_cost}'
                    )
                
                # Log completion
                OrderLog.objects.create(
                    purchase_order=po,
                    po_item=po_item,
                    action='completed',
                    performed_by=completed_by,
                    notes=f'Created purchaseItem with {quantity} units @ {cost_per_unit} each'
                )
        finally:
            # Re-enable signal
            post_save.connect(purchase_item_post_save, sender=purchaseItem)
        
        # Mark PO as completed
        po.status = 'completed'
        po.completed_by = completed_by
        po.completed_date = timezone.now()
        po.save()
        
        # Automatically mark all inventory units as ready_to_sale
        update_inventory_units_status(po, 'ready_to_sale', completed_by)
        
        OrderLog.objects.create(
            purchase_order=po,
            action='completed',
            performed_by=completed_by,
            notes=f'Converted to Purchase #{purchase.id}'
        )
        
        return purchase


def update_po_item_quantity(po_item, new_quantity, updated_by='system'):
    """Update ordered quantity in draft PO"""
    if po_item.purchase_order.status != 'draft':
        raise ValueError(f"Cannot update quantities in {po_item.purchase_order.status} order")
    
    with transaction.atomic():
        old_value = po_item.ordered_quantity
        po_item.ordered_quantity = new_quantity
        po_item.save()  # Triggers totals recalculation
        
        # Update PO totals
        update_po_totals(po_item.purchase_order)
        
        OrderLog.objects.create(
            purchase_order=po_item.purchase_order,
            po_item=po_item,
            action='quantity_changed',
            performed_by=updated_by,
            field_name='ordered_quantity',
            old_value=str(old_value),
            new_value=str(new_quantity)
        )


def update_po_item_cost(po_item, new_cost, updated_by='system'):
    """Update cost per unit in draft PO"""
    if po_item.purchase_order.status != 'draft':
        raise ValueError(f"Cannot update costs in {po_item.purchase_order.status} order")
    
    with transaction.atomic():
        old_value = po_item.ordered_cost_per_unit
        po_item.ordered_cost_per_unit = Decimal(str(new_cost))
        po_item.save()  # Triggers totals recalculation
        
        # Update PO totals
        update_po_totals(po_item.purchase_order)
        
        OrderLog.objects.create(
            purchase_order=po_item.purchase_order,
            po_item=po_item,
            action='cost_changed',
            performed_by=updated_by,
            field_name='ordered_cost_per_unit',
            old_value=str(old_value),
            new_value=str(new_cost)
        )


def update_received_quantity(po_item, received_quantity, updated_by='system'):
    """Update received quantity in received or sent PO"""
    if po_item.purchase_order.status not in ['sent', 'received']:
        raise ValueError(f"Cannot update received quantities in {po_item.purchase_order.status} order")
    
    with transaction.atomic():
        old_value = po_item.received_quantity
        po_item.received_quantity = received_quantity
        po_item.save()  # Triggers totals recalculation
        
        # Update PO totals
        update_po_totals(po_item.purchase_order)
        
        OrderLog.objects.create(
            purchase_order=po_item.purchase_order,
            po_item=po_item,
            action='received_qty_changed',
            performed_by=updated_by,
            field_name='received_quantity',
            old_value=str(old_value),
            new_value=str(received_quantity)
        )


def update_received_cost(po_item, received_cost_per_unit, updated_by='system'):
    """Update received cost per unit in received or sent PO"""
    if po_item.purchase_order.status not in ['sent', 'received']:
        raise ValueError(f"Cannot update received costs in {po_item.purchase_order.status} order")
    
    with transaction.atomic():
        old_value = po_item.received_cost_per_unit
        po_item.received_cost_per_unit = Decimal(str(received_cost_per_unit))
        po_item.save()  # Triggers totals recalculation
        
        # Update PO totals
        update_po_totals(po_item.purchase_order)
        
        OrderLog.objects.create(
            purchase_order=po_item.purchase_order,
            po_item=po_item,
            action='received_cost_changed',
            performed_by=updated_by,
            field_name='received_cost_per_unit',
            old_value=str(old_value),
            new_value=str(received_cost_per_unit)
        )


def update_po_totals(po):
    """Recalculate and update PO totals from items"""
    with transaction.atomic():
        total_items = 0
        total_ordered_cost = Decimal('0')
        total_received_cost = Decimal('0')
        
        for item in po.items.all():
            total_items += item.ordered_quantity
            total_ordered_cost += item.ordered_total
            if item.received_quantity > 0:
                total_received_cost += item.received_total
        
        po.total_items = total_items
        po.total_ordered_cost = total_ordered_cost
        po.total_received_cost = total_received_cost
        po.save()
