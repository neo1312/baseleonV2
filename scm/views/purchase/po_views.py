"""
Purchase Order creation and management views.
Provides simple UI for creating, managing, and receiving purchase orders.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal
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
        for p in products:
            faltante = getattr(p, 'faltante1', 0)
            if faltante and faltante != 'no' and faltante != 0:
                quantity_needed = int(faltante) * int(getattr(p, 'unidadEmpaque', 1))
                provider_cost = float(p.get_provider_cost(provider))
                items.append({
                    'id': p.id,
                    'name': p.full_name,
                    'sku': p.get_pv1(provider),
                    'available_stock': p.stock_ready_to_sale,
                    'costo': provider_cost,
                    'quantity_needed': quantity_needed,
                    'packaging_unit': int(getattr(p, 'unidadEmpaque', 1)),
                })
        
        return JsonResponse({
            'provider_id': provider.id,
            'provider_name': provider.name,
            'method': method,
            'items': items,
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
                
                items_data.append({
                    'product': p,
                    'pv1': p.get_pv1(provider),
                    'quantity_needed': quantity,
                    'quantity': quantity,
                    'cost_per_unit': cost_per_unit,
                    'total': quantity * cost_per_unit,
                })
            except DemandForecast.DoesNotExist:
                # Skip products without forecasts
                pass
    else:
        # Manual method: Show products with faltante > 0
        for p in products:
            faltante = getattr(p, 'faltante1', 0)
            if faltante and faltante != 'no' and faltante != 0:
                unidad_empaque = int(getattr(p, 'unidadEmpaque', 1))
                package_qty = int(faltante)  # Number of packages to order
                pieces_needed = package_qty * unidad_empaque  # Total pieces
                cost_per_piece = p.get_provider_cost(provider)  # Cost per piece
                cost_per_package = cost_per_piece * unidad_empaque  # Cost per package
                
                items_data.append({
                    'product': p,
                    'pv1': p.get_pv1(provider),
                    'quantity_needed': pieces_needed,
                    'quantity': package_qty,
                    'cost_per_unit': cost_per_package,
                    'total': package_qty * cost_per_package,
                })
    
    context = {
        'title': f'PO for {provider.name} ({method.upper()})',
        'provider': provider,
        'method': method,
        'items': items_data,
        'cart_total': sum(item['total'] for item in items_data),
    }
    
    return render(request, 'purchase/po/items.html', context)


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
                    unidad_empaque = int(getattr(product, 'unidadEmpaque', 1))
                    actual_qty = int(qty) * unidad_empaque
                    cost_per_piece = Decimal(str(cost or 0)) / unidad_empaque
                    items_data.append({
                        'product_id': product_id,
                        'quantity': actual_qty,
                        'cost_per_unit': cost_per_piece,
                    })
            
            if not items_data:
                messages.warning(request, 'No items selected')
                return redirect(f'scm:po_items_list', provider_id=provider_id)
            
            po = create_po_from_manual(provider, items_data, created_by=str(request.user))
        
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
        # Process received quantities and costs
        try:
            # Always update quantities and costs first
            for po_item in po.items.all():
                qty_key = f'received_qty_{po_item.id}'
                cost_key = f'received_cost_{po_item.id}'
                
                if qty_key in request.POST:
                    received_qty = int(request.POST.get(qty_key, 0))
                    if received_qty > 0:
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
            
            # Handle action
            if action == 'receive' and po.status == 'sent':
                receive_purchase_order(po, received_by=str(request.user))
                messages.success(request, f'PO {po.po_number} marked as received. Edit quantities/costs if needed.')
                return redirect('scm:po_receive', po_id=po_id)
                
            elif action == 'complete' and po.status == 'received':
                purchase = complete_purchase_order(po, completed_by=str(request.user))
                messages.success(request, f'PO {po.po_number} completed. Purchase #{purchase.id} created with inventory items ready for sale.')
                return redirect('scm:po_placed_orders')
            else:
                messages.error(request, 'Invalid action for current PO status')
            
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
    
    context = {
        'title': f'Receive {po.po_number}',
        'po': po,
        'can_complete': po.status == 'received',
    }
    
    return render(request, 'purchase/po/receive.html', context)


def po_delete(request, po_id):
    """Delete a purchase order (only allowed for approved or sent status)"""
    po = get_object_or_404(PurchaseOrder, id=po_id)
    
    if request.method == 'POST':
        # Only allow deletion of approved or sent orders
        if po.status not in ['approved', 'sent']:
            messages.error(request, f'Cannot delete PO with status "{po.get_status_display()}". Only approved or sent orders can be deleted.')
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
    """Create instant purchase order - show provider selection"""
    providers = Provider.objects.all()
    context = {
        'title': 'Instant Purchase Order',
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
                'product_name': product.full_name,
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
    """Create and complete instant purchase order"""
    if request.method == 'POST':
        try:
            provider_id = request.POST.get('provider_id')
            items_json = request.POST.get('items')  # JSON string of items
            
            if not provider_id or not items_json:
                return JsonResponse({'error': 'Missing provider or items'}, status=400)
            
            import json
            items = json.loads(items_json)
            
            if not items:
                return JsonResponse({'error': 'No items provided'}, status=400)
            
            provider = get_object_or_404(Provider, id=provider_id)
            
            # Create PO
            from django.db import transaction
            with transaction.atomic():
                # Generate PO number
                last_po = PurchaseOrder.objects.order_by('-id').first()
                po_number = f"INST-{timezone.now().strftime('%Y%m%d')}-{(last_po.id if last_po else 0) + 1:05d}"
                
                po = PurchaseOrder.objects.create(
                    po_number=po_number,
                    provider=provider,
                    status='completed',
                    order_type='instant',
                    created_by=request.user.username if request.user.is_authenticated else 'System',
                    completed_by=request.user.username if request.user.is_authenticated else 'System',
                    completed_date=timezone.now(),
                )
                
                total_cost = Decimal('0')
                total_quantity = 0
                
                # Add items and create inventory units
                for item in items:
                    product = get_object_or_404(Product, id=item['product_id'])
                    quantity = int(item['quantity'])
                    cost = Decimal(str(item['cost']))
                    
                    # Create PO item
                    po_item = PurchaseOrderItem.objects.create(
                        purchase_order=po,
                        product=product,
                        ordered_quantity=quantity,
                        ordered_cost_per_unit=cost,
                        ordered_total=quantity * cost,
                    )
                    
                    # Create inventory units (mark as received immediately for instant orders)
                    for i in range(quantity):
                        # Generate unique tracking ID: PO#-Product#-Sequential
                        tracking_id = f"PO{po.id}-P{product.id}-{i+1}"
                        
                        # Ensure uniqueness by checking for duplicates
                        counter = 1
                        base_tracking_id = tracking_id
                        while InventoryUnit.objects.filter(tracking_id=tracking_id).exists():
                            tracking_id = f"{base_tracking_id}-{counter}"
                            counter += 1
                        
                        InventoryUnit.objects.create(
                            product=product,
                            purchase_order=po,
                            purchase_item=None,  # Not using old purchaseItem model for PO workflow
                            status='ready_to_sale',  # Instantly ready for instant orders
                            purchase_cost=cost,
                            received_cost=cost,
                            received_date=timezone.now(),
                            tracking_id=tracking_id,
                        )
                    
                    # NOTE: Stock is now tracked only via InventoryUnit.objects.filter(status='ready_to_sale')
                    # Product.stock field removed - InventoryUnit is single source of truth
                    
                    total_cost += po_item.ordered_total
                    total_quantity += quantity
                
                # Update PO totals
                po.total_items = total_quantity
                po.total_ordered_cost = total_cost
                po.total_received_cost = total_cost
                po.received_date = timezone.now()
                po.save()
                
            return JsonResponse({
                'success': True,
                'po_id': po.id,
                'po_number': po.po_number,
                'message': f'Instant PO {po.po_number} created and completed',
            })
        
        except Exception as e:
            return JsonResponse({'error': f'Error: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)
