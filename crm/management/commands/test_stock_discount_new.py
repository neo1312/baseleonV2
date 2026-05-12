from django.core.management.base import BaseCommand
from crm.models import Sale, Client, saleItem
from im.models import Product

class Command(BaseCommand):
    help = 'Test stock discount functionality using new InventoryUnit-based stock system'

    def handle(self, *args, **options):
        # Get data
        client = Client.objects.first()
        product = Product.objects.first()

        if not client or not product:
            self.stdout.write(self.style.ERROR('No client or product found'))
            return

        self.stdout.write(f'✓ Client: {client.name}')
        self.stdout.write(f'✓ Product: {product.name} (Stock: {product.stock_ready_to_sale})\n')

        # Create a test sale
        sale = Sale.objects.create(client=client, tipo='menudeo', monedero=False)
        self.stdout.write(f'✓ Sale created: {sale.id}')

        initial_stock = product.stock_ready_to_sale
        self.stdout.write(f'Initial stock: {initial_stock} (from InventoryUnit ready_to_sale)')

        # Add item
        self.stdout.write('⏳ Adding 5 units to sale...')
        item = saleItem.objects.create(
            product=product,
            sale=sale,
            quantity=5,
            cost=product.costo,
            margen=product.margen,
            sat=False
        )

        # Refresh and check the new stock (InventoryUnit signals should have updated it)
        product.refresh_from_db()
        final_stock = product.stock_ready_to_sale

        self.stdout.write(f'\nFinal stock: {final_stock}')
        self.stdout.write(f'Deducted: {initial_stock - final_stock} units')

        if final_stock == initial_stock - 5:
            self.stdout.write(self.style.SUCCESS('\n✅ SUCCESS! Stock discount working!'))
        else:
            self.stdout.write(self.style.WARNING(f'\n⚠️  Expected {initial_stock - 5}, got {final_stock}'))
            self.stdout.write('(InventoryUnit signal handlers manage stock now)')

        self.stdout.write('\nNOTE: Product.stock field has been removed.')
        self.stdout.write('All stock tracking is now via InventoryUnit model with status=ready_to_sale')
