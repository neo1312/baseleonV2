from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from decimal import Decimal, ROUND_HALF_UP
from im.models import Product, DespieceConfig, DespieceLog


def despiece_list(request):
    """
    List all despiece configs with search. Each row shows the source
    product, its available stock, and an action button to convert.
    Configs are managed via Django admin.
    """
    q = request.GET.get('q', '')
    configs = DespieceConfig.objects.select_related(
        'source_product', 'destination_product'
    ).all()

    if q:
        configs = configs.filter(
            Q(source_product__name__icontains=q) |
            Q(source_product__barcode__icontains=q) |
            Q(destination_product__name__icontains=q)
        )

    configs_with_stock = []
    for config in configs:
        available = config.source_product.stock_ready_to_sale
        dest_stock = config.destination_product.stock_ready_to_sale
        configs_with_stock.append((config, available, dest_stock))

    data = {
        'configs': configs_with_stock,
        'q': q,
        'title': 'Despiece de Productos',
        'entity': 'Despiece',
    }
    return render(request, 'product/despiece_list.html', data)


from django.utils import timezone
from scm.models import Provider, PurchaseOrder, PurchaseOrderItem

def _get_or_create_despiece_provider():
    name = 'Despiece'
    provider = Provider.objects.filter(name=name).first()
    if provider:
        return provider
    return Provider.objects.create(
        id='despiece',
        name=name,
        phoneNumber='0000',
    )

def _create_po_number():
    from datetime import datetime
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    po_number = f'DESPIECE-{ts}'
    while PurchaseOrder.objects.filter(po_number=po_number).exists():
        ts = datetime.now().strftime('%Y%m%d%H%M%S')
        po_number = f'DESPIECE-{ts}'
    return po_number

@transaction.atomic
def despiece_process(request, pk):
    """
    Process a despiece conversion: retire source InventoryUnits and
    create destination InventoryUnits (status ready_to_sale) linked to
    a PurchaseOrder from the 'Despiece' provider.
    """
    from im.models import InventoryUnit

    config = get_object_or_404(
        DespieceConfig.objects.select_related('source_product', 'destination_product'),
        pk=pk
    )

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        source_qty = Decimal(str(request.POST.get('source_quantity', 0)))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Cantidad inválida'}, status=400)

    if source_qty <= 0:
        return JsonResponse({'error': 'La cantidad debe ser mayor a 0'}, status=400)

    available = config.source_product.stock_ready_to_sale
    if source_qty > available:
        return JsonResponse({
            'error': f'Stock insuficiente. Disponible: {available} unidad(es) de {config.source_product.name}'
        }, status=400)

    # 1. Retire source InventoryUnits (FIFO)
    units_to_retire = InventoryUnit.objects.filter(
        product_id=config.source_product_id,
        status='ready_to_sale'
    ).order_by('date_created')[:int(source_qty)]

    retired_count = 0
    total_source_cost = Decimal('0')
    for unit in units_to_retire:
        unit.status = 'retired_converted'
        unit.save()
        retired_count += 1
        if unit.purchase_cost:
            total_source_cost += Decimal(str(unit.purchase_cost))

    actual_source = Decimal(str(retired_count))
    actual_dest = int(actual_source * config.units_per_source)

    # Cost per destination unit (split source cost across pieces, rounded to 2 decimals)
    if retired_count > 0 and total_source_cost > 0:
        cost_per_dest_unit = (total_source_cost / Decimal(str(actual_dest))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        cost_per_dest_unit = (Decimal(str(config.destination_product.costo or 0)) or Decimal('0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 2. Create Provider + PurchaseOrder + PurchaseOrderItem
    provider = _get_or_create_despiece_provider()
    now = timezone.now()

    total_cost = (cost_per_dest_unit * Decimal(str(actual_dest))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    purchase_order = PurchaseOrder.objects.create(
        po_number=_create_po_number(),
        provider=provider,
        status='completed',
        created_by=request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'system',
        received_by=request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'system',
        completed_by=request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'system',
        order_type='instant',
        received_date=now,
        completed_date=now,
        total_items=actual_dest,
        total_ordered_cost=total_cost,
        total_received_cost=total_cost,
    )

    po_item = PurchaseOrderItem.objects.create(
        purchase_order=purchase_order,
        product=config.destination_product,
        ordered_quantity=actual_dest,
        received_quantity=actual_dest,
        ordered_cost_per_unit=cost_per_dest_unit,
        received_cost_per_unit=cost_per_dest_unit,
        ordered_total=total_cost,
        received_total=total_cost,
    )

    # 3. Generate tracking IDs (find max numeric suffix to avoid collisions)
    all_tracking = InventoryUnit.objects.filter(
        product_id=config.destination_product_id
    ).values_list('tracking_id', flat=True)

    max_num = 0
    for tid in all_tracking:
        try:
            num = int(tid.split('-')[-1])
            if num > max_num:
                max_num = num
        except (ValueError, IndexError):
            pass
    next_num = max_num + 1

    dest_units = []
    for i in range(actual_dest):
        dest_units.append(InventoryUnit(
            tracking_id=f'{config.destination_product_id}-{next_num + i}',
            product_id=config.destination_product_id,
            status='ready_to_sale',
            purchase_cost=cost_per_dest_unit,
            received_cost=cost_per_dest_unit,
            purchase_order=purchase_order,
            purchase_item=None,
            ordered_date=now,
            received_date=now,
            ready_date=now,
            date_created=now,
            last_updated=now,
        ))
    InventoryUnit.objects.bulk_create(dest_units)

    # 4. Log the conversion
    DespieceLog.objects.create(
        config=config,
        source_quantity=actual_source,
        destination_quantity=actual_dest,
        user=request.user if request.user.is_authenticated else None,
    )

    return JsonResponse({
        'success': True,
        'source_quantity': float(actual_source),
        'destination_quantity': float(actual_dest),
        'destination_stock': config.destination_product.stock_ready_to_sale,
    })
