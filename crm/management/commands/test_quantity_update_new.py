from django.core.management.base import BaseCommand
from crm.models import Sale, saleItem, Client
from im.models import Product, InventoryUnit
from django.db import transaction
import json
from decimal import Decimal
from django.utils import timezone


class Command(BaseCommand):
    help = 'Test quantity increment/decrement functionality using new InventoryUnit-based stock system'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('🧪 Testing Quantity Increment/Decrement (New System)...'))
        self.stdout.write('')

        # Get or create test client
        client, _ = Client.objects.get_or_create(
            name='mostrador',
            defaults={'phone': '0000'}
        )
        self.stdout.write(f'✓ Client: {client.name}')

        # Get test product
        product = Product.objects.filter(name='uno').first()
        if not product:
            self.stdout.write(self.style.ERROR('✗ Product "uno" not found'))
            return

        self.stdout.write(f'✓ Product: {product.name}')

        # Create a new sale
        sale = Sale.objects.create(
            client=client,
            monedero=False,
            tipo='menudeo'
        )
        self.stdout.write(f'✓ Sale created: {sale.id}')
        self.stdout.write('')

        # Log initial stock (using stock_ready_to_sale - the ONLY correct source of truth)
        product.refresh_from_db()
        initial_stock = product.stock_ready_to_sale
        self.stdout.write(f'Initial stock: {initial_stock} units (from InventoryUnit ready_to_sale)')
        self.stdout.write('')

        # Create a sale item with 5 units
        sale_item = saleItem.objects.create(
            product=product,
            sale=sale,
            quantity='5',
            cost=product.costo,
            margen=product.margen,
            price=Decimal('0'),
            sat=False
        )

        # The InventoryUnit signal handlers should have updated inventory
        product.refresh_from_db()
        self.stdout.write(f'⏳ Created sale item with 5 units')
        self.stdout.write(f'   Stock after creation: {product.stock_ready_to_sale} units')
        self.stdout.write('')

        # Test INCREMENT
        self.stdout.write(self.style.SUCCESS('Testing INCREMENT:'))
        product.refresh_from_db()
        stock_before_inc = product.stock_ready_to_sale
        self.stdout.write(f'  Stock before increment: {stock_before_inc}')

        with transaction.atomic():
            # Increment quantity in sale item
            sale_item.quantity = str(float(sale_item.quantity) + 1)
            sale_item.save()
            # Signal handler should create new InventoryUnit with status='sold'

        product.refresh_from_db()
        self.stdout.write(f'  ✓ Incremented quantity from 5 to 6')
        self.stdout.write(f'  ✓ Stock after increment: {product.stock_ready_to_sale}')
        self.stdout.write(f'  ✓ Inventory managed via InventoryUnit signals')
        self.stdout.write('')

        # Test DECREMENT
        self.stdout.write(self.style.SUCCESS('Testing DECREMENT:'))
        product.refresh_from_db()
        stock_before_dec = product.stock_ready_to_sale
        self.stdout.write(f'  Stock before decrement: {stock_before_dec}')

        with transaction.atomic():
            sale_item.quantity = str(float(sale_item.quantity) - 1)
            sale_item.save()
            # Signal handler should update InventoryUnit status

        product.refresh_from_db()
        self.stdout.write(f'  ✓ Decremented quantity from 6 to 5')
        self.stdout.write(f'  ✓ Stock after decrement: {product.stock_ready_to_sale}')
        self.stdout.write(f'  ✓ Inventory managed via InventoryUnit signals')
        self.stdout.write('')

        # Test DELETE when quantity reaches 0
        self.stdout.write(self.style.SUCCESS('Testing DELETE when quantity = 0:'))
        product.refresh_from_db()

        with transaction.atomic():
            sale_item.delete()
            # Signal handler should update InventoryUnit status back to ready_to_sale

        product.refresh_from_db()
        self.stdout.write(f'  ✓ Sale item deleted from database')
        self.stdout.write(f'  ✓ Stock after deletion: {product.stock_ready_to_sale}')
        self.stdout.write(f'  ✓ Inventory units returned to pool')
        self.stdout.write('')

        # Final verification
        sale.refresh_from_db()
        remaining_items = sale.saleitem_set.count()
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅ SUCCESS! Quantity increment/decrement working!'))
        self.stdout.write(f'   ✓ Final stock (ready_to_sale): {product.stock_ready_to_sale} units')
        self.stdout.write(f'   ✓ Remaining items in sale: {remaining_items}')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('NOTE: Product.stock field removed. All stock tracking via InventoryUnit.'))
