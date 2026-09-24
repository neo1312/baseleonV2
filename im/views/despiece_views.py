from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from decimal import Decimal, ROUND_HALF_UP
from im.models import Product, DespieceConfig, DespieceLog, ProductProvider
from crm.decorators import role_required


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
        last_log = config.conversion_logs.filter(reverted=False).order_by('-date_created').first()
        configs_with_stock.append((config, available, dest_stock, last_log))

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

@csrf_exempt
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
            'error': f'Stock insuficiente. Disponible: {available} unidad(es) de {config.source_product.compose_name}'
        }, status=400)

    # 1. Retire source InventoryUnits (FIFO)
    units_to_retire = InventoryUnit.objects.filter(
        product_id=config.source_product_id,
        status='ready_to_sale'
    ).order_by('date_created')[:int(source_qty)]

    retired_count = 0
    total_source_cost = Decimal('0')
    retired_tracking_ids = []
    for unit in units_to_retire:
        unit.status = 'retired_converted'
        unit.save()
        retired_count += 1
        retired_tracking_ids.append(unit.tracking_id)
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
    # Query by tracking_id prefix (global unique constraint) not just same product
    all_tracking = InventoryUnit.objects.filter(
        tracking_id__startswith=f'{config.destination_product_id}-'
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
    dest_tracking_ids = []
    for i in range(actual_dest):
        tid = f'{config.destination_product_id}-{next_num + i}'
        dest_tracking_ids.append(tid)
        dest_units.append(InventoryUnit(
            tracking_id=tid,
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

    # 4. Log the conversion (with full traceability for revert)
    DespieceLog.objects.create(
        config=config,
        source_quantity=actual_source,
        destination_quantity=actual_dest,
        user=request.user if request.user.is_authenticated else None,
        source_unit_ids=retired_tracking_ids,
        destination_unit_ids=dest_tracking_ids,
    )

    return JsonResponse({
        'success': True,
        'source_quantity': float(actual_source),
        'destination_quantity': float(actual_dest),
        'destination_stock': config.destination_product.stock_ready_to_sale,
    })


@login_required
@role_required('Admin', 'Manager')
def despiece_source_search(request):
    """AJAX endpoint to search source products by clave, barcode, or name.
    Excludes products that already have a DespieceConfig (OneToOne source)."""
    q = request.GET.get('q', '').strip()

    if len(q) < 1:
        return JsonResponse({'results': []})

    products = Product.objects.filter(active=True).filter(
        Q(clave__icontains=q) |
        Q(barcode__icontains=q) |
        Q(name__icontains=q)
    )

    taken_sources = DespieceConfig.objects.values_list(
        'source_product_id', flat=True
    )
    products = products.exclude(id__in=taken_sources)
    products = products[:20]

    results = []
    for p in products:
        label = p.compose_name
        bits = []
        if p.clave:
            bits.append(f'Clave: {p.clave}')
        if p.barcode:
            bits.append(f'Código: {p.barcode}')
        if bits:
            label += f' ({"; ".join(bits)})'
        results.append({
            'id': p.id,
            'text': label,
            'clave': p.clave or '',
            'barcode': p.barcode or '',
            'stock': p.stock_ready_to_sale,
            'costo': float(p.costo or 0),
        })

    return JsonResponse({'results': results})


def _generate_unique_barcode(source, suffix):
    """Generate a unique barcode for the auto-created product."""
    base = f'{source.barcode}{suffix}' if source.barcode else f'DESP-{source.id}{suffix}'
    candidate = base
    counter = 2
    while Product.objects.filter(barcode=candidate).exists():
        candidate = f'{base}-{counter}'
        counter += 1
    return candidate


@login_required
@role_required('Admin', 'Manager')
@csrf_exempt
@transaction.atomic
def despiece_create(request):
    """
    Create a despiece config and auto-create the destination product
    (a GRANEL sellable piece) from a source bulk product.
    Also creates the ProductProvider for the destination linked to the
    'Despiece' provider with cost calculated from the source.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        source_product_id = int(request.POST.get('source_product_id', 0))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Producto origen inválido'}, status=400)

    source = get_object_or_404(Product, pk=source_product_id)

    if DespieceConfig.objects.filter(source_product=source).exists():
        return JsonResponse({
            'error': f'"{source.compose_name}" ya tiene un despiece configurado.'
        }, status=400)

    try:
        units_per_source = Decimal(str(request.POST.get('units_per_source', 0)))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Unidades por origen inválidas'}, status=400)

    if units_per_source <= 0:
        return JsonResponse({'error': 'Las unidades por origen deben ser mayores a 0'}, status=400)

    # Cost per piece is always auto-calculated from the source bulk cost
    source_cost = Decimal(str(source.costo or 0))
    cost_per_piece = (source_cost / units_per_source).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )

    # Price or margin: mutually exclusive, exactly one must be provided
    raw_price = request.POST.get('piece_price', '').strip()
    raw_margin = request.POST.get('piece_margin', '').strip()

    if raw_price and raw_margin:
        return JsonResponse({'error': 'Elige solo uno: precio o margen'}, status=400)
    if not raw_price and not raw_margin:
        return JsonResponse({'error': 'Especifica precio o margen'}, status=400)

    pricing_mode = 'margin'
    granel_pricing_mode = 'margin'
    margen = None
    margen_granel = None
    precio_manual = None
    precio_granel_manual = None

    if raw_price:
        try:
            precio = Decimal(str(raw_price))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Precio inválido'}, status=400)
        if precio < 0:
            return JsonResponse({'error': 'El precio no puede ser negativo'}, status=400)
        pricing_mode = 'price'
        granel_pricing_mode = 'price'
        precio_manual = precio
        precio_granel_manual = precio
    else:
        try:
            margen_val = Decimal(str(raw_margin))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Margen inválido'}, status=400)
        if margen_val < 0:
            return JsonResponse({'error': 'El margen no puede ser negativo'}, status=400)
        margen = str(margen_val)
        margen_granel = str(margen_val)

    # 1. Auto-create destination (GRANEL) product
    destination = Product.objects.create(
        name=f'{source.name} - GRANEL',
        clave=source.clave,
        barcode=_generate_unique_barcode(source, '-G'),
        active=True,
        Granel_Item=True,
        granel=True,
        minimo=0,
        costo=cost_per_piece,
        margen=margen or '0',
        margenMayoreo=source.margenMayoreo,
        margenGranel=margen_granel or '0',
        unidad='Pieza',
        category_id=source.category_id,
        brand_id=source.brand_id,
        pricing_mode=pricing_mode,
        mayoreo_pricing_mode='margin',
        granel_pricing_mode=granel_pricing_mode,
        precio_manual=precio_manual,
        precio_granel_manual=precio_granel_manual,
    )

    # 2. Create/update ProductProvider for destination (cost from source)
    provider = _get_or_create_despiece_provider()
    ProductProvider.objects.update_or_create(
        product=destination,
        provider=provider,
        defaults={
            'pv1': source.barcode,
            'bundle_price': cost_per_piece,
            'unidad_empaque': '1',
        }
    )

    # 3. Create the config (its save() re-runs the same idempotent update_or_create)
    config = DespieceConfig.objects.create(
        source_product=source,
        destination_product=destination,
        units_per_source=units_per_source,
        user=request.user if request.user.is_authenticated else None,
    )

    return JsonResponse({
        'success': True,
        'config_id': config.id,
        'product_id': destination.id,
        'name': destination.compose_name,
        'barcode': destination.barcode,
        'bundle_price': float(cost_per_piece),
    })


@login_required
@role_required('Admin', 'Manager')
@csrf_exempt
@transaction.atomic
def despiece_revert(request):
    """
    Revert the last non-reverted conversion of a despiece config.
    - Restores the retired source units back to 'ready_to_sale'.
    - Deletes the despiece PurchaseOrder (cascade removes the created destination units).
    - If any destination piece was sold/converted, it BLOCKS the revert (no changes made).
    """
    from im.models import InventoryUnit
    from scm.models import PurchaseOrder

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        config_id = int(request.POST.get('config_id', 0))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Configuración inválida'}, status=400)

    config = get_object_or_404(DespieceConfig, pk=config_id)

    log = DespieceLog.objects.filter(config=config, reverted=False).order_by('-date_created').first()
    if not log:
        return JsonResponse({'error': 'No hay conversión para revertir'}, status=400)

    source_ids = log.source_unit_ids or []
    dest_ids = log.destination_unit_ids or []

    dest_units = InventoryUnit.objects.filter(tracking_id__in=dest_ids)
    if dest_units.exists():
        non_saleable = dest_units.exclude(status='ready_to_sale')
        if non_saleable.exists():
            sold = non_saleable.filter(status='sold').count()
            others = non_saleable.exclude(status='sold').count()
            msg = 'No se puede revertir: piezas de la conversión ya vendidas' if sold else \
                  'No se puede revertir: piezas de la conversión ya modificadas/convertidas'
            return JsonResponse({'error': msg}, status=400)

    # Restore source units back to saleable inventory
    restored = 0
    for unit in InventoryUnit.objects.filter(tracking_id__in=source_ids):
        if unit.status == 'retired_converted':
            unit.status = 'ready_to_sale'
            unit.retired_date = None
            unit.save()
            restored += 1

    # Delete the despiece PO (cascade removes its items + the created destination units)
    dest_unit = dest_units.filter(purchase_order__isnull=False).first()
    if dest_unit and dest_unit.purchase_order_id:
        po = PurchaseOrder.objects.filter(pk=dest_unit.purchase_order_id).first()
        if po:
            po.delete()

    log.reverted = True
    log.save()

    return JsonResponse({
        'success': True,
        'source_restored': restored,
        'dest_removed': len(dest_ids),
        'source_stock': config.source_product.stock_ready_to_sale,
        'destination_stock': config.destination_product.stock_ready_to_sale,
    })
