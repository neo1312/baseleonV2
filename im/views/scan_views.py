"""
Scan Inventory Views
Mobile-first barcode scanning for physical inventory counts
"""

import json
import math
from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.utils import timezone

from im.models import InventoryAudit, AuditItem, Product, InventoryUnit, AdjustmentTransaction
from crm.decorators import role_required

MINIMUM_PERCENTAGE = 80


@require_http_methods(["GET"])
@role_required('Admin', 'Manager', 'Auditor')
def audit_scan(request, audit_id):
    """Mobile scan page for physical inventory"""
    audit = get_object_or_404(InventoryAudit, id=audit_id, audit_type='physical')
    counted_items = audit.items.select_related('product', 'product__brand').all()
    total_active = Product.objects.filter(active=True).count()
    counted_count = counted_items.count()
    percentage = math.floor(counted_count / total_active * 100) if total_active > 0 else 0

    # Auto-join user as collaborator when they access the scan page
    from django.db.utils import OperationalError
    try:
        audit.collaborators.add(request.user)
    except OperationalError:
        pass
    
    context = {
        'audit': audit,
        'counted_items': counted_items,
        'counted_count': counted_count,
        'total_active': total_active,
        'percentage': percentage,
        'min_percentage': MINIMUM_PERCENTAGE,
    }
    return render(request, 'audit/scan.html', context)


@require_http_methods(["GET"])
@role_required('Admin', 'Manager', 'Auditor')
def audit_scan_lookup(request):
    """AJAX: Find product by barcode or exact clave match"""
    q = request.GET.get('q', '').strip()
    audit_id = request.GET.get('audit_id')

    if not q or not audit_id:
        return JsonResponse({'found': False, 'error': 'Parámetros insuficientes'})

    product = Product.objects.filter(
        Q(barcode=q) | Q(clave__iexact=q)
    ).first()

    if not product:
        return JsonResponse({'found': False, 'error': 'Producto no encontrado'})

    audit = get_object_or_404(InventoryAudit, id=audit_id)
    system_count = product.stock_ready_to_sale

    existing_item = AuditItem.objects.filter(audit=audit, product=product).first()

    return JsonResponse({
        'found': True,
        'product': {
            'id': product.id,
            'name': product.name,
            'brand': product.brand.name if product.brand else '',
            'clave': product.clave or '',
            'barcode': product.barcode or '',
            'system_count': system_count,
        },
        'already_counted': existing_item is not None,
        'existing_count': existing_item.physical_count if existing_item else None,
        'existing_item_id': existing_item.id if existing_item else None,
        'inactive': not product.active,
    })


@require_http_methods(["POST"])
@role_required('Admin', 'Manager', 'Auditor')
def audit_scan_save(request, audit_id):
    """AJAX: Save or update physical count for a scanned product"""
    data = json.loads(request.body)
    product_id = data.get('product_id')
    physical_count = data.get('physical_count')

    if not product_id or physical_count is None:
        return JsonResponse({'success': False, 'error': 'Faltan datos'})

    audit = get_object_or_404(InventoryAudit, id=audit_id)
    product = get_object_or_404(Product, id=product_id)
    system_count = product.stock_ready_to_sale

    was_inactive = not product.active
    if was_inactive:
        product.active = True
        product.save()

    total_active = Product.objects.filter(active=True).count()

    try:
        item, created = AuditItem.objects.update_or_create(
            audit=audit,
            product=product,
            defaults={
                'system_count': system_count,
                'physical_count': physical_count,
                'adjustment_status': 'pending',
                'counted_by': str(request.user),
            }
        )

        discrepancy = physical_count - system_count

        if discrepancy > 0:
            ts = int(timezone.now().timestamp())
            for i in range(discrepancy):
                InventoryUnit.objects.create(
                    tracking_id=f"SCAN-{audit.id}-{product.id}-{ts}-{i}",
                    product=product,
                    status='ready_to_sale',
                    purchase_cost=product.costo or Decimal('0'),
                    received_cost=product.costo or Decimal('0'),
                    received_date=timezone.now(),
                )
        elif discrepancy < 0:
            units_to_retire = InventoryUnit.objects.filter(
                product=product,
                status='ready_to_sale'
            ).order_by('received_date')[:abs(discrepancy)]
            for unit in units_to_retire:
                unit.status = 'retired_correction'
                unit.retired_date = timezone.now()
                unit.save()

        if discrepancy != 0:
            AdjustmentTransaction.objects.create(
                audit_item=item,
                product=product,
                adjustment_reason='correction',
                quantity_adjusted=discrepancy,
                unit_cost=product.costo or Decimal('0'),
                recorded_by=str(request.user),
                status='applied',
                applied_by=str(request.user),
                applied_at=timezone.now(),
            )

        item.adjustment_status = 'applied'
        item.save()

        return JsonResponse({
            'success': True,
            'created': created,
            'item_id': item.id,
            'product_name': product.name,
            'physical_count': physical_count,
            'system_count': system_count,
            'discrepancy': discrepancy,
            'inventory_adjusted': discrepancy != 0,
            'was_inactive': was_inactive,
            'total_active': total_active,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["POST"])
@role_required('Admin', 'Manager', 'Auditor')
def audit_scan_finish(request, audit_id):
    """Mark a physical audit as complete (requires 80%+ coverage)"""
    audit = get_object_or_404(InventoryAudit, id=audit_id, audit_type='physical')

    total_active = Product.objects.filter(active=True).count()
    counted_count = audit.items.count()
    percentage = math.floor(counted_count / total_active * 100) if total_active > 0 else 0

    if percentage < MINIMUM_PERCENTAGE:
        return JsonResponse({
            'success': False,
            'error': f'Debes inventariar al menos el {MINIMUM_PERCENTAGE}% de los productos. '
                     f'Actualmente llevas {percentage}% ({counted_count} de {total_active}).',
        })

    audit.status = 'under_review'
    audit.save()
    audit.update_stats()
    return JsonResponse({'success': True, 'redirect_url': f'/im/audit/{audit_id}/review/'})
