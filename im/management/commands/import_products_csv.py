import csv
from django.core.management.base import BaseCommand, CommandError
from im.models import Product, Category, Brand
from scm.models import Provider
from decimal import Decimal

class Command(BaseCommand):
    help = 'Import products from CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')
        parser.add_argument('--skip-errors', action='store_true', help='Skip rows with errors')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        skip_errors = options['skip_errors']
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                created = 0
                updated = 0
                errors = 0
                
                for row_num, row in enumerate(reader, start=2):  # start=2 because header is row 1
                    try:
                        product_data = self._parse_row(row)
                        product, is_new = Product.objects.update_or_create(
                            barcode=product_data['barcode'],
                            defaults=product_data
                        )
                        
                        if is_new:
                            created += 1
                            self.stdout.write(f"✓ Created: {product.name} (ID: {product.id})")
                        else:
                            updated += 1
                            self.stdout.write(f"↻ Updated: {product.name} (ID: {product.id})")
                            
                    except Exception as e:
                        errors += 1
                        error_msg = f"✗ Row {row_num}: {str(e)}"
                        if skip_errors:
                            self.stdout.write(self.style.WARNING(error_msg))
                        else:
                            raise CommandError(error_msg)
                
                # Summary
                self.stdout.write(self.style.SUCCESS(
                    f"\n✓ Import complete!\n"
                    f"  Created: {created}\n"
                    f"  Updated: {updated}\n"
                    f"  Errors: {errors}"
                ))
                
        except FileNotFoundError:
            raise CommandError(f'File not found: {csv_file}')

    def _parse_row(self, row):
        """Parse a CSV row into product data"""
        data = {}
        
        # Required fields
        data['name'] = row.get('name', '').strip()
        data['barcode'] = row.get('barcode', '').strip()
        
        if not data['name']:
            raise ValueError("Missing required field: name")
        if not data['barcode']:
            raise ValueError("Missing required field: barcode")
        
        # Numeric fields
        data['costo'] = Decimal(row.get('costo', 0) or 0)
        data['margen'] = row.get('margen', 0) or 0
        data['margenMayoreo'] = row.get('margenMayoreo', 0) or 0
        data['margenGranel'] = row.get('margenGranel', 0) or 0
        data['monedero_percentaje'] = row.get('monedero_percentaje', 0) or 0
        data['stockMax'] = int(row.get('stockMax', 0) or 0)
        data['stockMin'] = int(row.get('stockMin', 0) or 0)
        data['minimo'] = int(row.get('minimo', 0) or 0)
        
        # Boolean fields
        data['active'] = self._parse_bool(row.get('active', 'TRUE'))
        data['sat'] = self._parse_bool(row.get('sat', 'FALSE'))
        data['granel'] = self._parse_bool(row.get('granel', 'FALSE'))
        
        # String fields
        data['unidad'] = row.get('unidad', 'Pieza').strip()
        data['unidadEmpaque'] = row.get('unidadEmpaque', '1').strip()
        
        # Foreign key fields
        category_id = row.get('category')
        if category_id:
            try:
                data['category'] = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                raise ValueError(f"Category not found: {category_id}")
        
        brand_name = row.get('brand')
        if brand_name:
            try:
                data['brand'] = Brand.objects.get(name=brand_name)
            except Brand.DoesNotExist:
                raise ValueError(f"Brand not found: {brand_name}")
        
        provider_id = row.get('provedor')
        if provider_id:
            try:
                data['provedor'] = Provider.objects.get(id=provider_id)
            except Provider.DoesNotExist:
                raise ValueError(f"Provider not found: {provider_id}")
        
        return data

    def _parse_bool(self, value):
        """Convert string to boolean"""
        if isinstance(value, bool):
            return value
        return str(value).lower().strip() in ('true', '1', 'yes', 'on')
