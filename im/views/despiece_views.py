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

    try:
        piece_cost = Decimal(str(request.POST.get('piece_cost', 0)) or 0)
        piece_margin = Decimal(str(request.POST.get('piece_margin', 0)) or 0)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Costo o margen inválidos'}, status=400)

    if piece_cost < 0 or piece_margin < 0:
        return JsonResponse({'error': 'Costo y margen no pueden ser negativos'}, status=400)

    # 1. Auto-create destination (GRANEL) product
    destination = Product.objects.create(
        name=f'{source.name} - GRANEL',
        clave=source.clave,
        barcode=_generate_unique_barcode(source, '-G'),
        active=True,
        Granel_Item=True,
        granel=True,
        minimo=0,
        costo=piece_cost,
        margen=str(piece_margin),
        margenMayoreo=source.margenMayoreo,
        margenGranel=str(piece_margin),
        unidad='Pieza',
        category_id=source.category_id,
        brand_id=source.brand_id,
        pricing_mode='margin',
        mayoreo_pricing_mode='margin',
        granel_pricing_mode='margin',
    )

    # 2. Create/update ProductProvider for destination (cost from source)
    provider = _get_or_create_despiece_provider()
    source_cost = Decimal(str(source.costo or 0))
    bundle_price = (source_cost / units_per_source).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    ProductProvider.objects.update_or_create(
        product=destination,
        provider=provider,
        defaults={
            'pv1': source.barcode,
            'bundle_price': bundle_price,
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
        'bundle_price': float(bundle_price),
    })
