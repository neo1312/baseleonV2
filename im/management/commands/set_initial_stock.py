"""Set initial stock (stock/stockMax/stockMin) and price margin for products from a CSV file.

Search order per CSV row: product.barcode (exact), then ProductProvider.pv1.
Rows with no match are ignored. Products in the DB not present in the CSV
are set to stock=0, stockMax=0, stockMin=0.

Optional CSV column: margen (decimal, e.g. 0.45). When present for a matched
product, sets pricing_mode='margin' and updates the regular margin. Mayoreo
and granel pricing are NOT touched.

Usage:
  python manage.py set_initial_stock --csv file.csv            # dry-run preview
  python manage.py set_initial_stock --csv file.csv --apply    # apply changes
"""
import csv
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from im.models import Product, ProductProvider, InventoryUnit


class Command(BaseCommand):
    help = 'Set initial stock/stockMax/stockMin from CSV (dry-run by default, --apply to execute)'

    def add_arguments(self, parser):
        parser.add_argument('--csv', required=True, help='Path to CSV file')
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Apply changes. Without this flag it only previews.',
        )

    def handle(self, *args, **options):
        csv_path = options['csv']
        apply_mode = options['apply']

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = [self._parse_row(row, i + 2) for i, row in enumerate(reader)]
        except FileNotFoundError:
            raise CommandError(f'File not found: {csv_path}')

        valid_rows = [r for r in rows if r is not None]
        if not valid_rows:
            raise CommandError('No valid rows found in CSV. Required columns: barcode, stock, stockMax, stockMin')

        mode = 'APPLY' if apply_mode else 'DRY-RUN (no changes will be made)'
        self.stdout.write(f'{"=" * 70}')
        self.stdout.write(f' set_initial_stock — mode: {mode}')
        self.stdout.write(f' Rows in CSV: {len(valid_rows)}')
        self.stdout.write(f'{"=" * 70}')

        matched_ids = set()
        stats = {
            'matched': 0,
            'no_match_rows': 0,
            'skipped_rows': 0,
            'created_units': 0,
            'retired_units': 0,
            'errors': 0,
        }

        for row in valid_rows:
            try:
                self._process_row(row, matched_ids, stats, apply_mode)
            except Exception as e:
                stats['errors'] += 1
                self.stdout.write(self.style.ERROR(
                    f'  ✗ Row {row["line"]}: {e}'
                ))

        self.stdout.write('')
        self.stdout.write(f'{"-" * 70}')
        self.stdout.write(' Products WITHOUT match in CSV -> will be zeroed:')
        self.stdout.write(f'{"-" * 70}')
        zero_candidates = Product.objects.filter(active=True).exclude(id__in=matched_ids)
        total_zero = 0
        for product in zero_candidates:
            current_stock = product.stock_ready_to_sale
            action = 'zero stock' if (current_stock > 0 or product.stockMax or product.stockMin) else 'no change'
            if current_stock > 0:
                total_zero += current_stock
            self.stdout.write(
                f'  • {self._product_label(product)}: stock {current_stock}→0, '
                f'stockMax {product.stockMax}→0, stockMin {product.stockMin}→0  [{action}]'
            )
            if apply_mode and action != 'no change':
                self._zero_product(product)
                self.stdout.write(self.style.SUCCESS(f'    ✓ applied'))

        self.stdout.write('')
        self.stdout.write(f'{"=" * 70}')
        self.stdout.write(' SUMMARY')
        self.stdout.write(f'{"=" * 70}')
        self.stdout.write(f'  Matched & processed   : {stats["matched"]}')
        self.stdout.write(f'  Rows without match    : {stats["no_match_rows"]} (ignored)')
        self.stdout.write(f'  Rows skipped (errors) : {stats["skipped_rows"]}')
        self.stdout.write(f'  InventoryUnits created: {stats["created_units"]}')
        self.stdout.write(f'  InventoryUnits retired: {stats["retired_units"]}')
        self.stdout.write(f'  Products to be zeroed : {zero_candidates.count()} ({total_zero} units)')
        if stats['errors']:
            self.stdout.write(self.style.ERROR(f'  Errors               : {stats["errors"]}'))
        self.stdout.write(f'{"=" * 70}')

        if not apply_mode:
            self.stdout.write(self.style.WARNING(
                '\n  Preview only. Re-run with --apply to apply the changes.'
            ))

    def _parse_row(self, row, line):
        barcode = (row.get('barcode') or '').strip()
        pv1 = (row.get('pv1') or '').strip()
        stock = (row.get('stock') or '').strip()
        stock_max = (row.get('stockMax') or row.get('stock_max') or '').strip()
        stock_min = (row.get('stockMin') or row.get('stock_min') or '').strip()
        margen = (row.get('margen') or '').strip()

        if not barcode and not pv1:
            return None

        try:
            stock_i = int(float(stock)) if stock else 0
        except (ValueError, TypeError):
            stock_i = 0
        try:
            stock_max_i = int(float(stock_max)) if stock_max else 0
        except (ValueError, TypeError):
            stock_max_i = 0
        try:
            stock_min_i = int(float(stock_min)) if stock_min else 0
        except (ValueError, TypeError):
            stock_min_i = 0

        if stock_min_i > stock_max_i:
            stock_min_i, stock_max_i = stock_max_i, stock_min_i

        margen_dec = None
        if margen:
            try:
                margen_dec = Decimal(margen)
            except (ValueError, TypeError):
                margen_dec = None

        return {
            'line': line,
            'barcode': barcode,
            'pv1': pv1,
            'stock': stock_i,
            'stockMax': stock_max_i,
            'stockMin': stock_min_i,
            'margen': margen_dec,
        }

    def _resolve_product(self, row):
        if row['barcode']:
            product = Product.objects.filter(barcode=row['barcode']).first()
            if product:
                return product
        if row['pv1']:
            pp = ProductProvider.objects.filter(pv1=row['pv1']).select_related('product').first()
            if pp:
                return pp.product
        return None

    def _process_row(self, row, matched_ids, stats, apply_mode):
        product = self._resolve_product(row)
        if not product:
            stats['no_match_rows'] += 1
            self.stdout.write(self.style.WARNING(
                f'  - Row {row["line"]}: no match (barcode="{row["barcode"]}" pv1="{row["pv1"]}") -> ignored'
            ))
            return

        matched_ids.add(product.id)
        current_stock = product.stock_ready_to_sale
        target_stock = row['stock']
        to_create = max(0, target_stock - current_stock)
        to_retire = max(0, current_stock - target_stock)

        self.stdout.write(
            f'  • {self._product_label(product)}'
        )
        self.stdout.write(
            f'      stock    : {current_stock} → {target_stock}'
            f'  ({"create " + str(to_create) if to_create else "no change"}'
            f'{" / retire " + str(to_retire) if to_retire else ""})'
        )
        self.stdout.write(
            f'      stockMax : {product.stockMax} → {row["stockMax"]}'
            f'  | stockMin: {product.stockMin} → {row["stockMin"]}'
        )
        if row['margen'] is not None:
            current_margen = product.margen
            self.stdout.write(
                f'      margen   : {current_margen} → {row["margen"]}'
                f'  | pricing_mode: {product.pricing_mode} → margin'
            )

        if not apply_mode:
            stats['matched'] += 1
            return

        product.stockMax = row['stockMax']
        product.stockMin = row['stockMin']
        update_fields = ['stockMax', 'stockMin', 'last_updated']
        if row['margen'] is not None:
            product.pricing_mode = 'margin'
            product.margen = str(row['margen'])
            update_fields += ['pricing_mode', 'margen']
        product.save(update_fields=update_fields)

        if to_create > 0:
            for i in range(to_create):
                InventoryUnit.objects.create(
                    tracking_id=f'INIT-{product.id}-{timezone.now().strftime("%Y%m%d%H%M%S")}-{i}',
                    product=product,
                    status='ready_to_sale',
                    purchase_cost=product.costo or Decimal('0'),
                    received_cost=product.costo or Decimal('0'),
                    received_date=timezone.now(),
                    ready_date=timezone.now(),
                )
            stats['created_units'] += to_create

        if to_retire > 0:
            units = InventoryUnit.objects.filter(
                product=product,
                status='ready_to_sale',
            ).order_by('received_date')[:to_retire]
            for unit in units:
                unit.status = 'retired_correction'
                unit.retired_date = timezone.now()
                unit.save()
            stats['retired_units'] += to_retire

        stats['matched'] += 1
        self.stdout.write(self.style.SUCCESS(f'      ✓ applied'))

    def _zero_product(self, product):
        units = InventoryUnit.objects.filter(
            product=product,
            status='ready_to_sale',
        )
        for unit in units:
            unit.status = 'retired_correction'
            unit.retired_date = timezone.now()
            unit.save()
        if product.stockMax or product.stockMin:
            product.stockMax = 0
            product.stockMin = 0
            product.save(update_fields=['stockMax', 'stockMin', 'last_updated'])

    def _product_label(self, product):
        name = product.compose_name[:50]
        bits = []
        if product.clave:
            bits.append(product.clave)
        if product.barcode:
            bits.append(product.barcode)
        return f'{name} ({" / ".join(bits)})' if bits else name