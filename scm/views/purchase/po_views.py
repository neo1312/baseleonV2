"""
Purchase Order creation and management views.
Provides simple UI for creating, managing, and receiving purchase orders.
"""
import logging

logger = logging.getLogger(__name__)

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal
from django.db.models import Q
from django.db import transaction
from scm.models import Provider, PurchaseOrder, PurchaseOrderItem
from im.models import Product, DemandForecast, ProductProvider, InventoryUnit
from scm.po_operations import (
    create_po_from_manual,
    create_po_from_forecast,
    approve_purchase_order,
    send_purchase_order,
    receive_purchase_order,
    update_received_quantity,
    update_received_cost,
    complete_purchase_order,
)
from scm.po_pdf import generate_po_pdf
from scm.po_whatsapp import send_po_via_whatsapp


def _barcode_sort_key(barcode):
    """Sort barcodes numerically when possible, lexicographically otherwise."""
    try:
        return (0, int(str(barcode)))
    except (ValueError, TypeError):
        return (1, str(barcode or ''))


def po_create(request):
    """Initial PO creation page - select provider and method"""
    providers = Provider.objects.all()
    context = {
        'title': 'Create Purchase Order',
        'providers': providers,
    }
    return render(request, 'purchase/po/create.html', context)


def po_select_provider(request):
    """AJAX endpoint to get provider and prepare items list"""
    if request.method == 'GET':
        provider_id = request.GET.get('provider_id')
        method = request.GET.get('method')  # 'manual' or 'auto'
        
        if not provider_id or not method:
            return JsonResponse({'error': 'Missing parameters'}, status=400)
        
        provider = get_object_or_404(Provider, id=provider_id)
        
        # Get products that have a ProductProvider entry for this provider
        from im.models import ProductProvider
        product_ids = ProductProvider.objects.filter(provider=provider).values_list('product_id', flat=True)
        products = Product.objects.filter(id__in=product_ids, active=True)
        
        # Filter by stock needed (faltante1 != 0 and != 'no')
        items = []
        seen_groups = set()
        for p in products:
            # Skip if this product's group was already handled
            if p.group and p.group.id in seen_groups:
                continue
            faltante = getattr(p, 'faltante1', 0)
            if faltante and faltante != 'no' and faltante != 0:
                if p.group:
                    seen_groups.add(p.group.id)
                pp_unidad = p.get_unidad_empaque(provider)
                quantity_needed = int(faltante) * pp_unidad
                provider_per_piece = float(p.get_provider_cost(provider))
                items.append({
                    'id': p.id,
                    'name': p.name,
                    'sku': p.get_pv1(provider),
                    'barcode': p.barcode,
                    'available_stock': p.stock_ready_to_sale,
                    'group_stock': sum(m.stock_ready_to_sale for m in p.group.products.all()) if p.group else None,
                    'costo': provider_per_piece,
                    'quantity_needed': quantity_needed,
                    'packaging_unit': pp_unidad,
                })
        
        return JsonResponse({
            'provider_id': provider.id,
            'provider_name': provider.name,
            'method': method,
            'items': sorted(items, key=lambda x: _barcode_sort_key(x.get('sku', ''))),
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


def po_items_list(request, provider_id):
    """Display items needing order with editable quantities"""
    provider = get_object_or_404(Provider, id=provider_id)
    method = request.GET.get('method', 'manual')
    
    # Get products that have a ProductProvider entry for this provider
    from im.models import ProductProvider
    product_ids = ProductProvider.objects.filter(provider=provider).values_list('product_id', flat=True)
    products = Product.objects.filter(id__in=product_ids, active=True)
    
    # Prepare items data
    items_data = []
    
    if method == 'auto':
        # Auto method: Show all products with DemandForecast using EOQ
        for p in products:
            try:
                forecast = DemandForecast.objects.get(product=p)
                quantity = int(forecast.eoq or 10)  # Default to 10 if EOQ not set
                cost_per_unit = p.get_provider_cost(provider)
                
                unit_sin_iva = cost_per_unit / Decimal('1.16')
                items_data.append({
                    'product': p,
                    'pv1': p.get_pv1(provider),
                    'quantity_needed': quantity,
                    'quantity': quantity,
                    'cost_per_unit': cost_per_unit,
                    'unit_sin_iva': unit_sin_iva,
                    'iva_amount': cost_per_unit - unit_sin_iva,
                    'total': quantity * cost_per_unit,
                })
            except DemandForecast.DoesNotExist:
                # Skip products without forecasts
                pass
    else:
        # Manual method: Show products with faltante > 0 (user can add more manually)
        import math
        seen_groups = set()
        for p in products:
            if p.group and p.group.id in seen_groups:
                continue
            faltante = getattr(p, 'faltante1', 0)
            if faltante and faltante != 'no' and faltante != 0:
                if p.group:
                    seen_groups.add(p.group.id)
                pp_unidad = p.get_unidad_empaque(provider)
                pieces_needed = int(faltante)
                package_qty = math.ceil(pieces_needed / pp_unidad)
                cost_per_piece = p.get_provider_cost(provider)
                cost_per_package = cost_per_piece * pp_unidad

                unit_sin_iva = cost_per_package / Decimal('1.16')
                items_data.append({
                    'product': p,
                    'pv1': p.get_pv1(provider),
                    'quantity_needed': pieces_needed,
                    'quantity': package_qty,
                    'cost_per_unit': cost_per_package,
                    'unit_sin_iva': unit_sin_iva,
                    'iva_amount': cost_per_package - unit_sin_iva,
                    'unidad_empaque': pp_unidad,
                    'total': package_qty * cost_per_package,
                    'group_stock': sum(m.stock_ready_to_sale for m in p.group.products.all()) if p.group else None,
                    'group_min': p.group.stockMin if p.group else None,
                    'group_max': p.group.stockMax if p.group else None,
                })
    
    items_data.sort(key=lambda x: _barcode_sort_key(x['pv1']))

    context = {
        'title': f'PO for {provider.name} ({method.upper()})',
        'provider': provider,
        'method': method,
        'items': items_data,
        'cart_total': sum(item['total'] for item in items_data),
    }
    
    return render(request, 'purchase/po/items.html', context)


def po_search_product(request):
    """AJAX: search products from a provider by barcode or name"""
    provider_id = request.GET.get('provider_id')
    q = request.GET.get('q', '').strip()
    if not provider_id or not q:
        return JsonResponse({'results': []})
    from im.models import ProductProvider
    products = Product.objects.filter(
        provider_pairs__provider_id=provider_id,
        active=True,
    ).filter(
        Q(barcode__icontains=q) | Q(name__icontains=q)
    ).order_by('barcode')[:20]
    results = []
    for p in products:
        pp = ProductProvider.objects.filter(provider_id=provider_id, product=p).first()
        results.append({
            'id': p.id,
            'barcode': p.barcode,
            'pv1': pp.pv1 if pp else '',
            'name': p.name,
            'cost': float(p.get_provider_cost(provider_id)),
            'unidad_empaque': int(p.get_unidad_empaque(provider_id) or 1),
        })
    return JsonResponse({'results': results})


def po_submit(request):
    """Process PO submission"""
    if request.method != 'POST':
        return redirect('scm:po_create')
    
    provider_id = request.POST.get('provider_id')
    method = request.POST.get('method')
    
    if not provider_id or not method:
        messages.error(request, 'Invalid parameters')
        return redirect('scm:po_create')
    
    provider = get_object_or_404(Provider, id=provider_id)
    
    try:
        if method == 'auto':
            # Create auto PO from forecast
            po = create_po_from_forecast(provider, created_by=str(request.user))
        else:
            # Create manual PO from form data
            items_data = []
            # Parse POST data for items
            product_ids = request.POST.getlist('product_id')
            quantities = request.POST.getlist('quantity')
            costs = request.POST.getlist('cost')
            
            for product_id, qty, cost in zip(product_ids, quantities, costs):
                if qty and int(qty) > 0:
                    product = Product.objects.get(id=product_id)
                    pp_unidad = product.get_unidad_empaque(provider)
                    actual_qty = int(qty) * pp_unidad
                    cost_per_piece = Decimal(str(cost or 0)) / pp_unidad
                    items_data.append({
                        'product_id': product_id,
                        'quantity': actual_qty,
                        'cost_per_unit': cost_per_piece,
                    })
            
            if not items_data:
                messages.warning(request, 'No items selected')
                return redirect(f'scm:po_items_list', provider_id=provider_id)
            
            po = create_po_from_manual(provider, items_data, created_by=str(request.user))
        
        # Set IVA flag from form
        po.has_iva = request.POST.get('has_iva') == '1'
        po.save(update_fields=['has_iva'])
        
        # Approve the PO immediately
        approve_purchase_order(po, approved_by=str(request.user))
        
        # Count created inventory units
        from im.models import InventoryUnit
        units_count = InventoryUnit.objects.filter(purchase_order=po).count()
        
        messages.success(request, f'Purchase Order {po.po_number} created with {po.items.count()} items and {units_count} inventory tracking units ready for shipment.')
        return redirect('scm:po_placed_orders')
        
    except Exception as e:
        messages.error(request, f'Error creating PO: {str(e)}')
        return redirect('scm:po_create')


def po_placed_orders(request):
    """Display list of approved/sent/received/completed purchase orders with optional date and status filtering"""
    from datetime import datetime, timedelta
    from django.utils import timezone
    
    pos = PurchaseOrder.objects.filter(
        status__in=['approved', 'sent', 'received', 'completed']
    ).order_by('-created_date')
    
    # Get status filter parameter
    status_filter = request.GET.get('status', '')
    if status_filter in ['approved', 'sent', 'received', 'completed']:
        pos = pos.filter(status=status_filter)
    
    # Get date filter parameters - default to today
    today = timezone.localtime(timezone.now()).date()
    date_from = request.GET.get('date_from', today.strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            pos = pos.filter(created_date__date__gte=from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            # Add 1 day to include the entire end date
            to_date = to_date + timedelta(days=1)
            pos = pos.filter(created_date__date__lt=to_date)
        except ValueError:
            pass
    
    context = {
        'title': 'Placed Orders',
        'purchase_orders': pos,
        'date_from': date_from,
        'date_to': date_to,
        'status_filter': status_filter,
    }
    
    return render(request, 'purchase/po/placed.html', context)


def po_send(request, po_id):
    """Send a purchase order to supplier (approved -> sent) with PDF via WhatsApp"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    # Get send method from POST data
    send_method = request.POST.get('send_method', 'pdf') if request.method == 'POST' else 'pdf'
    
    try:
        # Transition PO status (always happens)
        send_purchase_order(po, sent_by=str(request.user))
        
        # Generate PDF if requested
        pdf_content = None
        if send_method in ['pdf', 'both']:
            pdf_content = generate_po_pdf(po)
        
        # Send WhatsApp if requested
        whatsapp_result = None
        if send_method in ['whatsapp', 'both']:
            if not pdf_content:
                pdf_content = generate_po_pdf(po)
            whatsapp_result = send_po_via_whatsapp(po, pdf_content)
        
        # If PDF-only method, return the PDF as download
        if send_method == 'pdf':
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="PO-{po.po_number}.pdf"'
            return response
        
        # Show appropriate message based on send method and results
        if send_method == 'whatsapp':
            if whatsapp_result and whatsapp_result['sent_via'] == 'whatsapp':
                messages.success(
                    request,
                    f"✓ PO {po.po_number} sent successfully via WhatsApp to {po.provider.phoneNumber}"
                )
            elif whatsapp_result and whatsapp_result['sent_via'] == 'not_sent':
                messages.warning(
                    request,
                    f"✓ PO {po.po_number} status updated to 'sent' (WhatsApp not configured - development mode)"
                )
            else:
                messages.warning(
                    request,
                    f"✓ PO {po.po_number} status updated. WhatsApp delivery failed: {whatsapp_result.get('message', 'Unknown error') if whatsapp_result else 'Error'}"
                )
        else:  # both
            if whatsapp_result and whatsapp_result['sent_via'] == 'whatsapp':
                messages.success(
                    request,
                    f"✓ PO {po.po_number} sent successfully via PDF and WhatsApp to {po.provider.phoneNumber}"
                )
            elif whatsapp_result and whatsapp_result['sent_via'] == 'not_sent':
                messages.warning(
                    request,
                    f"✓ PO {po.po_number} PDF ready (WhatsApp not configured - development mode)"
                )
            else:
                messages.warning(
                    request,
                    f"✓ PO {po.po_number} PDF generated. WhatsApp delivery failed: {whatsapp_result.get('message', 'Unknown error') if whatsapp_result else 'Error'}"
                )
            
    except Exception as e:
        messages.error(request, f'Error sending PO: {str(e)}')
    
    return redirect('scm:po_placed_orders')


def po_receive(request, po_id):
    """Receive a purchase order with quantity/cost modifications"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if request.method == 'POST':
        action = request.POST.get('action', 'receive')
        try:
            with transaction.atomic():
                # Update quantities and costs from POST data
                po_items_all = sorted(po.items.all(), key=lambda x: _barcode_sort_key(x.product.get_pv1(po.provider)))
                for po_item in po_items_all:
                    qty_key = f'received_qty_{po_item.id}'
                    cost_key = f'received_cost_{po_item.id}'
                    
                    if qty_key in request.POST:
                        received_qty_str = request.POST.get(qty_key, '')
                        received_qty = int(received_qty_str) if received_qty_str else 0
                        update_received_quantity(po_item, received_qty, updated_by=str(request.user))
                    
                    if cost_key in request.POST:
                        received_cost_str = request.POST.get(cost_key, '')
                        if received_cost_str:
                            try:
                                received_cost = Decimal(str(received_cost_str))
                                if received_cost > 0:
                                    update_received_cost(po_item, received_cost, updated_by=str(request.user))
                            except:
                                pass
                
                # Handle action within same transaction
                if action == 'receive' and po.status == 'sent':
                    receive_purchase_order(po, received_by=str(request.user))
                    tx_message = 'success'
                    tx_success = f'PO {po.po_number} marked as received. Edit quantities/costs if needed.'
                    tx_redirect = 'scm:po_receive'
                    tx_redirect_id = po_id
                    
                elif action == 'complete' and po.status == 'received':
                    purchase = complete_purchase_order(po, completed_by=str(request.user))
                    tx_message = 'success'
                    tx_success = f'PO {po.po_number} completed. Purchase #{purchase.id} created with inventory items ready for sale.'
                    tx_redirect = 'scm:po_placed_orders'
                    tx_redirect_id = None
                    
                elif action == 'receive' and po.status == 'received':
                    # Edit mode: quantities already saved above, just refresh
                    tx_message = 'success'
                    tx_success = f'PO {po.po_number} quantities updated.'
                    tx_redirect = 'scm:po_receive'
                    tx_redirect_id = po_id
                    
                else:
                    tx_message = 'error'
                    tx_success = f'Invalid action "{action}" for PO status "{po.get_status_display()}".'
                    tx_redirect = 'scm:po_placed_orders'
                    tx_redirect_id = None
            
            # Handle redirect/message after transaction commits
            if tx_message == 'success':
                messages.success(request, tx_success)
            else:
                messages.error(request, tx_success)
            
            if tx_redirect_id:
                return redirect(tx_redirect, po_id=tx_redirect_id)
            return redirect(tx_redirect)
            
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    
    po_items = list(po.items.select_related('product').all())
    po_items.sort(key=lambda x: _barcode_sort_key(x.product.get_pv1(po.provider)))

    # Add IVA breakdown for each item
    for item in po_items:
        item.unit_sin_iva = item.ordered_cost_per_unit / Decimal('1.16')
        item.iva_amount = item.ordered_cost_per_unit - item.unit_sin_iva

    context = {
        'title': f'Receive {po.po_number}',
        'po': po,
        'po_items': po_items,
        'can_complete': po.status == 'received',
    }
    
    return render(request, 'purchase/po/receive.html', context)


def po_delete(request, po_id):
    """Delete a purchase order (allowed for approved, sent, or received status)"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if request.method == 'POST':
        # Allow deletion of approved, sent, received, or completed orders
        if po.status not in ['approved', 'sent', 'received', 'completed']:
            messages.error(request, f'Cannot delete PO with status "{po.get_status_display()}". Only approved, sent, or received orders can be deleted.')
            return redirect('scm:po_placed_orders')
        
        try:
            po_number = po.po_number
            # Cascade delete will handle:
            # - PurchaseOrderItems
            # - InventoryUnits (via FK with CASCADE)
            po.delete()
            messages.success(request, f'PO {po_number} and all associated inventory units have been deleted.')
        except Exception as e:
            messages.error(request, f'Error deleting PO: {str(e)}')
        
        return redirect('scm:po_placed_orders')
    
    # If GET request, show placed orders (form should only POST)
    return redirect('scm:po_placed_orders')


def po_upload_csv(request):
    """Upload CSV to create a purchase order"""
    providers = Provider.objects.all()

    if request.method == 'POST':
        provider_id = request.POST.get('provider_id')
        csv_file = request.FILES.get('csv')

        if not provider_id or not csv_file:
            messages.error(request, 'Select a provider and upload a CSV file')
            return redirect('scm:po_upload_csv')

        provider = get_object_or_404(Provider, id=provider_id)

        try:
            if csv_file.size > 10 * 1024 * 1024:
                messages.error(request, 'File too large (max 10 MB).')
                return redirect('scm:po_upload_csv')
        except Exception:
            pass

        try:
            rows, errors = _parse_po_csv(csv_file, provider)
        except Exception as e:
            logger.error('PO CSV parse error: %s', e, exc_info=True)
            messages.error(request, 'Error parsing CSV: {}'.format(e))
            return redirect('scm:po_upload_csv')

        if errors:
            for err in errors:
                messages.error(request, err)
            return redirect('scm:po_upload_csv')

        if not rows:
            messages.error(request, 'No valid rows found in CSV')
            return redirect('scm:po_upload_csv')

        session_rows = [
            {
                'product_id': r['product_id'],
                'product_name': r['product'].name,
                'pv1': r['pv1'],
                'quantity': r['quantity'],
                'cost': str(r['cost']),
                'total': str(r['total']),
            }
            for r in rows
        ]

        # Add IVA breakdown to rows for template display
        for r in rows:
            cost_dec = r['cost']
            unit_sin_iva = cost_dec / Decimal('1.16')
            r['iva_amount'] = cost_dec - unit_sin_iva
        request.session['po_csv_data'] = {
            'provider_id': provider.id,
            'provider_name': provider.name,
            'rows': session_rows,
        }

        context = {
            'title': 'Verify CSV Data',
            'provider': provider,
            'rows': rows,
            'total': sum(r['total'] for r in rows),
        }
        return render(request, 'purchase/po/upload_csv_preview.html', context)

    context = {
        'title': 'Upload CSV - Purchase Order',
        'providers': providers,
    }
    return render(request, 'purchase/po/upload_csv.html', context)


def _parse_po_csv(csv_file, provider):
    """Parse CSV file and return (rows, errors). Each row: {product, product_id, pv1, quantity, cost, total}"""
    import csv
    from io import TextIOWrapper
    from im.models import ProductProvider

    rows = []
    errors = []
    reader = csv.DictReader(TextIOWrapper(csv_file, encoding='utf-8-sig'))

    for i, row in enumerate(reader, start=2):
        pv1 = (row.get('pv1') or '').strip()
        qty_str = (row.get('quantity') or '').strip()
        cost_str = (row.get('cost') or '').strip()

        if not pv1:
            errors.append(f'Row {i}: missing pv1')
            continue

        if not qty_str:
            errors.append(f'Row {i}: missing quantity')
            continue

        try:
            quantity = int(qty_str)
            if quantity <= 0:
                errors.append(f'Row {i}: quantity must be > 0')
                continue
        except ValueError:
            errors.append(f'Row {i}: quantity must be a whole number')
            continue

        pp = ProductProvider.objects.filter(pv1=pv1, provider=provider).select_related('product').first()
        if not pp:
            errors.append(f'Row {i}: PV1 "{pv1}" not found for {provider.name}')
            continue

        product = pp.product
        try:
            cost = Decimal(cost_str) if cost_str else product.get_provider_cost(provider)
        except Exception as exc:
            logger.warning('Row %s: cost parse failed (%s), using default provider cost', i, exc)
            try:
                cost = product.get_provider_cost(provider)
            except Exception as exc2:
                logger.error('Row %s: could not get provider cost either: %s', i, exc2)
                errors.append('Row {}: invalid cost and no default cost available'.format(i))
                continue

        rows.append({
            'product': product,
            'product_id': product.id,
            'pv1': pv1,
            'quantity': quantity,
            'cost': cost,
            'total': quantity * cost,
        })

    return rows, errors


def po_upload_csv_confirm(request):
    """Confirm CSV data and create the purchase order"""
    data = request.session.pop('po_csv_data', None)
    if not data:
        messages.error(request, 'No CSV data found. Please upload again.')
        return redirect('scm:po_upload_csv')

    provider = get_object_or_404(Provider, id=data['provider_id'])
    items_data = [
        {'product_id': r['product_id'], 'quantity': r['quantity'], 'cost_per_unit': str(r['cost'])}
        for r in data['rows']
    ]

    try:
        po = create_po_from_manual(provider, items_data, created_by=str(request.user))
        po.has_iva = request.POST.get('has_iva') == '1'
        po.save(update_fields=['has_iva'])
        approve_purchase_order(po, approved_by=str(request.user))

        units_count = InventoryUnit.objects.filter(purchase_order=po).count()
        messages.success(
            request,
            f'PO {po.po_number} created from CSV with {po.items.count()} items and {units_count} inventory units.'
        )
        return redirect('scm:po_placed_orders')
    except Exception as e:
        logger.error('PO CSV confirm error: %s', e, exc_info=True)
        messages.error(request, f'Error creating PO: {str(e)}')
        return redirect('scm:po_upload_csv')


def test_whatsapp(request):
    """Test WhatsApp integration (development/debugging)"""
    import os
    
    context = {
        'title': 'Test WhatsApp',
        'account_sid_set': bool(os.getenv('WHATSAPP_ACCOUNT_SID', '').strip()),
        'auth_token_set': bool(os.getenv('WHATSAPP_AUTH_TOKEN', '').strip()),
        'from_number': os.getenv('WHATSAPP_FROM_NUMBER', '').strip(),
    }
    
    if request.method == 'POST':
        po_id = request.POST.get('po_id')
        send_method = request.POST.get('send_method', 'both')
        
        if not po_id:
            messages.error(request, 'Please select a purchase order')
            return render(request, 'purchase/po/test_whatsapp.html', context | {'purchase_orders': PurchaseOrder.objects.all()})
        
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        # Check credentials
        account_sid = os.getenv('WHATSAPP_ACCOUNT_SID', '').strip()
        auth_token = os.getenv('WHATSAPP_AUTH_TOKEN', '').strip()
        from_number = os.getenv('WHATSAPP_FROM_NUMBER', '').strip()
        
        if not all([account_sid, auth_token, from_number]):
            messages.error(request, 'WhatsApp not configured. Set environment variables: WHATSAPP_ACCOUNT_SID, WHATSAPP_AUTH_TOKEN, WHATSAPP_FROM_NUMBER')
            context['purchase_orders'] = PurchaseOrder.objects.all()
            return render(request, 'purchase/po/test_whatsapp.html', context)
        
        try:
            # Generate PDF if requested
            pdf_content = None
            if send_method in ['pdf', 'both']:
                pdf_content = generate_po_pdf(po)
            
            # Send via WhatsApp if requested
            result = None
            if send_method in ['whatsapp', 'both']:
                result = send_po_via_whatsapp(po, pdf_content)
                
                if result['success']:
                    messages.success(request, f"✓ {result['message']}")
                else:
                    messages.error(request, f"✗ {result['message']}")
            
            if send_method == 'pdf' and pdf_content:
                messages.success(request, f"✓ PDF generated ({len(pdf_content)} bytes)")
            
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        
        context['purchase_orders'] = PurchaseOrder.objects.all()
        return render(request, 'purchase/po/test_whatsapp.html', context)
    
    # GET request
    context['purchase_orders'] = PurchaseOrder.objects.all()
    return render(request, 'purchase/po/test_whatsapp.html', context)


def po_instant_create(request):
    """Manual order - select provider and add items"""
    providers = Provider.objects.all()
    context = {
        'title': 'Manual Purchase Order',
        'providers': providers,
    }
    return render(request, 'purchase/po/instant_create_standalone.html', context)


def po_instant_lookup_pv1(request):
    """AJAX endpoint to validate PV1 and get product details"""
    if request.method == 'GET':
        pv1 = request.GET.get('pv1', '').strip()
        provider_id = request.GET.get('provider_id')
        
        if not pv1 or not provider_id:
            return JsonResponse({'error': 'Missing PV1 or provider'}, status=400)
        
        try:
            provider = Provider.objects.get(id=provider_id)
            # Find ProductProvider entry for this PV1 and provider
            product_provider = ProductProvider.objects.select_related('product').get(
                pv1=pv1,
                provider=provider
            )
            product = product_provider.product
            cost = float(product.get_provider_cost(provider))
            
            return JsonResponse({
                'success': True,
                'product_id': product.id,
                'product_name': product.name,
                'pv1': product_provider.pv1,
                'cost': cost,
                'unit': product.unidad,
            })
        except ProductProvider.DoesNotExist:
            return JsonResponse({'error': f'PV1 {pv1} not found for this provider'}, status=404)
        except Exception as e:
            return JsonResponse({'error': f'Error: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


def po_instant_submit(request):
    """Create purchase order following normal workflow (draft -> approve)"""
    if request.method == 'POST':
        try:
            provider_id = request.POST.get('provider_id')
            items_json = request.POST.get('items')

            if not provider_id or not items_json:
                return JsonResponse({'error': 'Missing provider or items'}, status=400)

            import json
            items = json.loads(items_json)

            if not items:
                return JsonResponse({'error': 'No items provided'}, status=400)

            provider = get_object_or_404(Provider, id=provider_id)

            items_data = [
                {'product_id': int(item['product_id']), 'quantity': int(item['quantity']), 'cost_per_unit': str(item['cost'])}
                for item in items
            ]

            po = create_po_from_manual(provider, items_data, created_by=str(request.user))
            po.has_iva = request.POST.get('has_iva') == '1'
            po.save(update_fields=['has_iva'])
            approve_purchase_order(po, approved_by=str(request.user))

            return JsonResponse({
                'success': True,
                'po_id': po.id,
                'po_number': po.po_number,
                'message': f'PO {po.po_number} created and approved — ready to send',
            })

        except Exception as e:
            return JsonResponse({'error': f'Error: {str(e)}'}, status=500)

    return JsonResponse({'error': 'Invalid request'}, status=400)


def po_instant_full_create(request):
    """Instant order page — user scans PV1 and adds items, then submits"""
    providers = Provider.objects.all()
    context = {
        'title': 'Instant Order',
        'providers': providers,
    }
    return render(request, 'purchase/po/instant_full.html', context)


def po_instant_full_submit(request):
    """Instant order submit — full workflow draft -> approved -> sent -> received -> completed (ready to sale)"""
    if request.method == 'POST':
        try:
            provider_id = request.POST.get('provider_id')
            items_json = request.POST.get('items')

            if not provider_id or not items_json:
                return JsonResponse({'error': 'Missing provider or items'}, status=400)

            import json
            items = json.loads(items_json)

            if not items:
                return JsonResponse({'error': 'No items provided'}, status=400)

            provider = get_object_or_404(Provider, id=provider_id)

            items_data = [
                {'product_id': int(item['product_id']), 'quantity': int(item['quantity']), 'cost_per_unit': str(item['cost'])}
                for item in items
            ]

            po = create_po_from_manual(provider, items_data, created_by=str(request.user))
            po.has_iva = request.POST.get('has_iva') == '1'
            po.save(update_fields=['has_iva'])
            approve_purchase_order(po, approved_by=str(request.user))
            send_purchase_order(po, sent_by=str(request.user))
            receive_purchase_order(po, received_by=str(request.user))
            complete_purchase_order(po, completed_by=str(request.user))

            return JsonResponse({
                'success': True,
                'po_id': po.id,
                'po_number': po.po_number,
                'message': f'{po.total_items} items — all ready to sale!',
            })

        except Exception as e:
            logger.error('Instant order full submit failed: %s', e, exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request'}, status=400)
