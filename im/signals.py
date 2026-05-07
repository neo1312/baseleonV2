"""
Inventory tracking signals
Automatically manages InventoryUnit lifecycle based on purchase, sale, and devolution events
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender='scm.purchaseItem')
def purchase_item_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for purchaseItem.post_save
    Creates InventoryUnit records when purchase items are received
    Skips creation if units already exist for this product
    """
    from im.models import InventoryUnit
    from scm.models import purchaseItem
    
    # Skip if product not set or quantity is 0
    if not instance.product_id or not instance.quantity:
        return
    
    try:
        quantity = int(instance.quantity)
    except (ValueError, TypeError):
        logger.warning(f'Invalid quantity for purchaseItem {instance.id}')
        return
    
    if quantity <= 0:
        return
    
    with transaction.atomic():
        # Check if units already exist for this purchaseItem
        existing_units = InventoryUnit.objects.filter(purchase_item_id=instance.id)
        if existing_units.exists():
            logger.info(f'InventoryUnits already exist for purchaseItem {instance.id}, skipping creation')
            return
        
        # Get the next tracking ID
        last_unit = InventoryUnit.objects.filter(
            product_id=instance.product_id
        ).order_by('-tracking_id').first()
        
        if last_unit:
            try:
                last_num = int(last_unit.tracking_id.split('-')[-1])
                next_num = last_num + 1
            except (ValueError, IndexError):
                next_num = 1
        else:
            next_num = 1
        
        # Create InventoryUnit records for each physical unit
        created_units = []
        
        # Extract purchase cost from purchaseItem
        try:
            purchase_cost = Decimal(str(instance.cost)) if instance.cost else Decimal('0.00')
        except (ValueError, TypeError):
            purchase_cost = Decimal('0.00')
        
        for i in range(quantity):
            tracking_id = f'{instance.product_id}-{next_num + i}'
            
            unit = InventoryUnit.objects.create(
                tracking_id=tracking_id,
                product_id=instance.product_id,
                status='received',
                purchase_item=instance,
                ordered_date=instance.purchase.date_created,
                received_date=timezone.localtime(timezone.now()),
                purchase_cost=purchase_cost
            )
            created_units.append(unit)
        
        logger.info(f'Created {len(created_units)} InventoryUnits for purchaseItem {instance.id} at cost {purchase_cost}')


@receiver(post_save, sender='crm.saleItem')
def sale_item_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for saleItem.post_save
    Marks InventoryUnits as sold when a sale item is created
    """
    from im.models import InventoryUnit
    from crm.models import saleItem
    from im.abc_calculation import recalculate_abc
    
    # Skip if product not set or quantity is 0
    if not instance.product_id or not instance.quantity:
        return
    
    try:
        quantity = int(float(instance.quantity))
    except (ValueError, TypeError):
        logger.warning(f'Invalid quantity for saleItem {instance.id}')
        return
    
    if quantity <= 0:
        return
    
    with transaction.atomic():
        # Find oldest ready units (FIFO - First In, First Out)
        ready_units = InventoryUnit.objects.filter(
            product_id=instance.product_id,
            status='ready_to_sale'
        ).order_by('date_created')[:quantity]
        
        sold_count = 0
        for unit in ready_units:
            unit.status = 'sold'
            unit.sale_item = instance
            unit.sold_date = timezone.localtime(timezone.now())
            unit.save()
            sold_count += 1
        
        logger.info(f'Marked {sold_count} InventoryUnits as sold for saleItem {instance.id}')
        
        # Trigger ABC recalculation if auto-recalculate is enabled
        from im.models import ABCConfiguration
        config = ABCConfiguration.objects.first()
        if config and config.auto_recalculate:
            try:
                recalculate_abc()
            except Exception as e:
                logger.error(f'Error recalculating ABC after sale: {e}')


@receiver(post_save, sender='crm.devolutionItem')
def devolution_item_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for devolutionItem.post_save
    Reverts InventoryUnits from sold back to ready_to_sale when items are devolved
    """
    from im.models import InventoryUnit
    from crm.models import devolutionItem
    from im.abc_calculation import recalculate_abc
    
    # Skip if product not set or quantity is 0
    if not instance.product_id or not instance.quantity:
        return
    
    try:
        quantity = int(float(instance.quantity))
    except (ValueError, TypeError):
        logger.warning(f'Invalid quantity for devolutionItem {instance.id}')
        return
    
    if quantity <= 0:
        return
    
    with transaction.atomic():
        # Find most recently sold units (LIFO - Last In, First Out for devolutions)
        sold_units = InventoryUnit.objects.filter(
            product_id=instance.product_id,
            status='sold'
        ).order_by('-sold_date')[:quantity]
        
        reverted_count = 0
        for unit in sold_units:
            unit.status = 'ready_to_sale'
            unit.sale_item = None
            unit.sold_date = None
            unit.save()
            reverted_count += 1
        
        logger.info(f'Reverted {reverted_count} InventoryUnits to ready_to_sale for devolutionItem {instance.id}')
        
        # Trigger ABC recalculation if auto-recalculate is enabled
        from im.models import ABCConfiguration
        config = ABCConfiguration.objects.first()
        if config and config.auto_recalculate:
            try:
                recalculate_abc()
            except Exception as e:
                logger.error(f'Error recalculating ABC after devolution: {e}')


@receiver(post_delete, sender='crm.saleItem')
def sale_item_post_delete(sender, instance, **kwargs):
    """
    Signal handler for saleItem.post_delete
    If a sale item is deleted, revert its associated InventoryUnits back to ready_to_sale
    """
    from im.models import InventoryUnit
    from im.abc_calculation import recalculate_abc
    
    with transaction.atomic():
        # Find units associated with this sale item
        sold_units = InventoryUnit.objects.filter(
            sale_item_id=instance.id,
            status='sold'
        )
        
        reverted_count = 0
        for unit in sold_units:
            unit.status = 'ready_to_sale'
            unit.sale_item = None
            unit.sold_date = None
            unit.save()
            reverted_count += 1
        
        logger.info(f'Reverted {reverted_count} InventoryUnits due to saleItem deletion')
        
        # Trigger ABC recalculation if auto-recalculate is enabled
        from im.models import ABCConfiguration
        config = ABCConfiguration.objects.first()
        if config and config.auto_recalculate:
            try:
                recalculate_abc()
            except Exception as e:
                logger.error(f'Error recalculating ABC after sale deletion: {e}')

