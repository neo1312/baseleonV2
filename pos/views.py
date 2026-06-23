import json
import time
from decimal import Decimal
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from im.models import Product, DespieceConfig
from crm.models import Sale, saleItem, Client
from django.utils import timezone
from django.db import transaction
from crm.decorators import role_required

def _get_pos_context(request):
    """Shared helper to build POS context data."""
    all_products = list(Product.objects.filter(active=True)[:100])

    # Pre-load despiece configs keyed by destination product id
    despiece_map = {}
    for dc in DespieceConfig.objects.select_related('source_product').all():
        despiece_map[dc.destination_product_id] = dc

    # Include products with stock, granel items, or despiece-eligible (even at 0 stock)
    products = [
        p for p in all_products
        if p.stock_ready_to_sale > 0 or p.Granel_Item or p.id in despiece_map
    ]
    products.sort(key=lambda p: p.stock_ready_to_sale, reverse=True)
    clients = Client.objects.all()[:100]

    products_data = []
    for p in products:
        granel_price = p.priceListaGranel if p.priceListaGranel != 'N/A' else None
        available_stock = p.stock_ready_to_sale
        dc = despiece_map.get(p.id)
        products_data.append({
            'id': p.id,
            'barcode': p.barcode,
            'name': p.name,
            'brand': p.brand.name if p.brand else '',
            'compose_name': p.compose_name,
            'price': float(p.priceLista),
            'price_mayoreo': float(p.priceMayoreo),
            'price_granel': float(granel_price) if granel_price else None,
            'stock': available_stock,
            'granel': p.granel,
            'Granel_Item': p.Granel_Item,
            'minimo': p.minimo,
            'despiece_config_id': dc.id if dc else None,
            'despiece_source_name': dc.source_product.compose_name if dc else None,
            'despiece_source_id': dc.source_product.id if dc else None,
            'despiece_source_stock': dc.source_product.stock_ready_to_sale if dc else None,
            'despiece_units_per': float(dc.units_per_source) if dc else None,
        })
    return {
        'products': products_data,
        'clients': clients,
        'session_key': request.session.session_key,
    }

@login_required(login_url='/login/')
def pos_index(request):
    """Main POS interface"""
    context = {
        'title': 'POS - Point of Sale',
        **_get_pos_context(request),
    }
    return render(request, 'pos/index.html', context)

@login_required(login_url='/login/')
def pos_index_touch(request):
    """Touch-optimized POS interface for 10-inch tablets"""
    context = {
        'title': 'POS - Touch',
        **_get_pos_context(request),
    }
    return render(request, 'pos/index_touch.html', context)

@csrf_exempt
def search_products(request):
    """Search products by name (word match regardless of order), SKU, or barcode"""
    if request.method == 'GET':
        query = request.GET.get('q', '').strip()
        
        if not query:
            products = Product.objects.filter(active=True)[:50]
        else:
            # Split query into words, match any word in barcode/clave,
            # and require ALL words to appear in name (order-independent)
            words = query.split()
            
            filters = models.Q()
            for word in words:
                filters &= models.Q(name__icontains=word)
            
            filters |= models.Q(barcode__icontains=query)
            filters |= models.Q(clave__icontains=query)
            
            products = Product.objects.filter(active=True).filter(filters)[:50]
        
        # Pre-load despiece configs
        despiece_map = {}
        for dc in DespieceConfig.objects.select_related('source_product').all():
            despiece_map[dc.destination_product_id] = dc

        # Include products with stock, granel items, or despiece-eligible (even at 0 stock)
        products_list = [
            p for p in products
            if p.stock_ready_to_sale > 0 or p.Granel_Item or p.id in despiece_map
        ]
        products_list.sort(key=lambda p: p.stock_ready_to_sale, reverse=True)
        
        # Enrich with price data - USE STOCK_READY_TO_SALE (only source of truth)
        results = []
        for p in products_list:
            granel_price = p.priceListaGranel if p.priceListaGranel != 'N/A' else None
            available_stock = p.stock_ready_to_sale
            dc = despiece_map.get(p.id)
            results.append({
                'id': p.id,
                'barcode': p.barcode,
                'name': p.name,
                'brand': p.brand.name if p.brand else '',
                'compose_name': p.compose_name,
                'price': float(p.priceLista),
                'price_mayoreo': float(p.priceMayoreo),
                'price_granel': float(granel_price) if granel_price else None,
                'stock': available_stock,
                'granel': p.granel,
                'Granel_Item': p.Granel_Item,
                'minimo': p.minimo,
                'despiece_config_id': dc.id if dc else None,
                'despiece_source_name': dc.source_product.compose_name if dc else None,
                'despiece_source_id': dc.source_product.id if dc else None,
                'despiece_source_stock': dc.source_product.stock_ready_to_sale if dc else None,
                'despiece_units_per': float(dc.units_per_source) if dc else None,
            })
        
        return JsonResponse(results, safe=False)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def scan_product(request):
    """Lookup product by exact barcode match. Returns JSON or 404."""
    if request.method == 'GET':
        q = request.GET.get('q', '').strip()
        if not q:
            return JsonResponse({'error': 'No query'}, status=400)
        
        product = Product.objects.filter(barcode=q).first()
        if not product:
            return JsonResponse({'error': 'Not found'}, status=404)
        
        despiece_map = {}
        for dc in DespieceConfig.objects.select_related('source_product').all():
            despiece_map[dc.destination_product_id] = dc
        dc = despiece_map.get(product.id)
        
        available_stock = product.stock_ready_to_sale
        granel_price = product.priceListaGranel if product.priceListaGranel != 'N/A' else None
        
        return JsonResponse({
            'id': product.id,
            'barcode': product.barcode,
            'name': product.name,
            'compose_name': product.compose_name,
            'price': float(product.priceLista),
            'price_mayoreo': float(product.priceMayoreo),
            'price_granel': float(granel_price) if granel_price else None,
            'stock': available_stock,
            'granel': product.granel,
            'Granel_Item': product.Granel_Item,
            'minimo': product.minimo,
            'despiece_config_id': dc.id if dc else None,
            'despiece_source_name': dc.source_product.compose_name if dc else None,
            'despiece_source_id': dc.source_product.id if dc else None,
            'despiece_source_stock': dc.source_product.stock_ready_to_sale if dc else None,
            'despiece_units_per': float(dc.units_per_source) if dc else None,
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def debug_stock(request):
    """Debug endpoint - show all product stock from database (using stock_ready_to_sale)"""
    if request.method == 'GET':
        products = Product.objects.filter(active=True)
        
        stock_data = []
        for p in products:
            # Use stock_ready_to_sale - the ONLY source of truth
            available_stock = p.stock_ready_to_sale
            if available_stock > 0:  # Only show products with inventory
                stock_data.append({
                    'id': p.id,
                    'name': p.name,
                    'barcode': p.barcode,
                    'compose_name': p.compose_name,
                    'stock_ready_to_sale': available_stock,
                    'priceLista': float(p.priceLista),
                    'priceMayoreo': float(p.priceMayoreo),
                })
        
        return JsonResponse({
            'timestamp': timezone.now().isoformat(),
            'products': stock_data,
            'total': len(stock_data),
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def get_product_stock(request):
    """Get current product stock from database (single source of truth - InventoryUnit ready_to_sale)"""
    if request.method == 'GET':
        product_id = request.GET.get('id')
        
        try:
            product = Product.objects.get(id=product_id)
            available_stock = product.stock_ready_to_sale
            
            return JsonResponse({
                'id': product.id,
                'name': product.name,
                'compose_name': product.compose_name,
                'stock': available_stock,
                'success': True,
            })
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Product not found', 'success': False}, status=404)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def validate_stock(request):
    """Validate if cart items are still available (batch check)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            items = data.get('items', [])  # List of {product_id, quantity}
            
            validation_results = []
            for item in items:
                product_id = item.get('product_id')
                requested_qty = item.get('quantity', 0)
                
                try:
                    product = Product.objects.get(id=product_id)
                    available = product.stock_ready_to_sale
                    is_valid = available >= requested_qty
                    
                    validation_results.append({
                        'product_id': product_id,
                        'product_name': product.name,
                        'compose_name': product.compose_name,
                        'requested': requested_qty,
                        'available': available,  # NOW CORRECT - from InventoryUnit
                        'valid': is_valid,
                        'message': f'OK' if is_valid else f'Only {available} available'
                    })
                except Product.DoesNotExist:
                    validation_results.append({
                        'product_id': product_id,
                        'valid': False,
                        'message': 'Product not found'
                    })
            
            # Check if all items are valid
            all_valid = all(item['valid'] for item in validation_results)
            
            return JsonResponse({
                'success': all_valid,
                'items': validation_results,
            })
        except Exception as e:
            return JsonResponse({'error': str(e), 'success': False}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def get_product(request):
    """Get single product details"""
    if request.method == 'GET':
        product_id = request.GET.get('id')
        tipo = request.GET.get('tipo', 'menudeo')  # menudeo or mayoreo
        
        try:
            product = Product.objects.get(id=product_id)
            
            # Get price based on sale type
            if tipo == 'mayoreo':
                price = product.priceMayoreo
            else:  # menudeo (default)
                price = product.priceLista
            
            granel_price = product.priceListaGranel if product.priceListaGranel != 'N/A' else None
            
            return JsonResponse({
                'id': product.id,
                'barcode': product.barcode,
                'name': product.name,
                'compose_name': product.compose_name,
                'price': float(price),
                'price_granel': float(granel_price) if granel_price else None,
                'stock': product.stock_ready_to_sale,
                'granel': product.granel,
                'minimo': product.minimo,
            })
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
@transaction.atomic
def complete_sale(request):
    """Complete a sale"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            items = data.get('items', [])
            if not items:
                return JsonResponse({'error': 'No items in cart'}, status=400)
            
            payment_method = data.get('payment_method', 'cash')
            client_id = data.get('client_id')
            wallet_discount = Decimal(str(data.get('wallet_discount', 0)))
            
            # Get or create client
            if client_id:
                client = Client.objects.get(id=client_id)
            else:
                # Use default "mostrador" client for walk-in customers
                client, _ = Client.objects.get_or_create(
                    name='mostrador',
                    defaults={'phoneNumber': '0000', 'tipo': 'menudeo'}
                )
            
            # Create sale
            tipo = data.get('tipo', 'menudeo')  # menudeo or mayoreo
            
            sale = Sale.objects.create(
                client=client,
                payment_method=payment_method,
                tipo=tipo,
                date_created=timezone.now(),
                status='completed',
            )
            
            # Add items to sale and calculate total from actual backend prices
            total_quantity = 0
            total_amount = Decimal('0')  # Calculate on backend based on actual prices
            for item_data in items:
                product = Product.objects.get(id=item_data['product_id'])
                quantity = int(item_data['quantity'])
                
                # Calculate price based on sale type and granel rules
                if tipo == 'mayoreo':
                    price = Decimal(str(product.priceMayoreo))
                else:  # menudeo
                    # For menudeo, check granel quantity rules
                    if product.granel and quantity < int(product.minimo):
                        # Below minimum, use granel price (higher)
                        granel_price = product.priceListaGranel
                        price = Decimal(str(granel_price)) if granel_price != 'N/A' else Decimal(str(product.priceLista))
                    else:
                        # Normal price
                        price = Decimal(str(product.priceLista))
                
                # Validate stock (InventoryUnit ready_to_sale)
                if product.stock_ready_to_sale < quantity:
                    raise ValueError(f"Insufficient stock for {product.compose_name}")
                
                # Create sale item
                sale_item = saleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=quantity,
                    price=price,
                    sat=product.sat,
                )
                
                # NOTE: InventoryUnit signal handlers automatically manage inventory status changes
                # When saleItem is created, signals mark InventoryUnit records as 'sold'
                # Product.stock_ready_to_sale count decreases automatically
                
                # Calculate item total (price * quantity) for accurate backend total
                item_total = price * Decimal(str(quantity))
                total_amount += item_total
                total_quantity += quantity
            
            # Handle wallet discount if applied
            if wallet_discount > 0 and client_id:
                # Deduct from client's wallet
                if hasattr(client, 'monedero'):
                    client.monedero = Decimal(str(client.monedero or 0)) - wallet_discount
                    client.save()
                # Apply wallet discount to final total
                total_amount -= wallet_discount
            
            # Update sale totals with accurately calculated amounts
            sale.total_items = total_quantity
            sale.total_amount = total_amount
            sale.save()
            
            return JsonResponse({
                'success': True,
                'sale_id': sale.id,
                'message': f'Sale completed! Sale ID: {sale.id}',
                'total': float(total_amount),
            })
            
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Import models.Q for search
from django.db import models


@csrf_exempt
def cart_save(request):
    """Save current cart to session"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            request.session['pos_cart'] = data.get('cart', {})
            request.session['pos_sale_type'] = data.get('saleType')
            request.session['pos_client_id'] = data.get('clientId')
            request.session['pos_client_name'] = data.get('clientName')
            request.session['pos_client_wallet'] = data.get('clientWallet')
            request.session['pos_sale_started'] = data.get('saleStarted', False)
            request.session['pos_sale_completed'] = data.get('saleCompleted')

            # If sale completed flag is set, also clear checkout state and reset sale type
            if data.get('saleCompleted'):
                if 'pos_checkout_state' in request.session:
                    del request.session['pos_checkout_state']
                request.session['pos_sale_type'] = 'menudeo'

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)


def clean_pos_session(session, data):
    """Clean up stale/inconsistent POS session data and save if modified.
    Returns the (possibly cleaned) checkoutState or None.
    """
    modified = False
    checkout_state = data.get('pos_checkout_state')
    sale_started = data.get('pos_sale_started', False)
    sale_completed = data.get('pos_sale_completed')

    # Auto-clear saleCompleted older than 6 seconds
    if sale_completed:
        elapsed = time.time() - sale_completed.get('timestamp', 0)
        if elapsed >= 6:
            data.pop('pos_sale_completed', None)
            data.pop('pos_checkout_state', None)
            sale_completed = None
            checkout_state = None
            modified = True
        else:
            # saleCompleted is fresh — always clear checkout state
            if checkout_state:
                data.pop('pos_checkout_state', None)
                checkout_state = None
                modified = True

    # If checkout is active but sale is not started (no saleCompleted), it's stale
    if checkout_state and checkout_state.get('active') and not sale_started:
        checkout_state = None
        data.pop('pos_checkout_state', None)
        modified = True

    if modified:
        Store = Session.objects.get_session_store_class()
        session.session_data = Store().encode(data)
        session.save()

    return checkout_state


def get_session_data(session_key):
    """Helper to read pos data from a session by session_key"""
    try:
        session = Session.objects.get(session_key=session_key)
        data = session.get_decoded()
        checkout_state = clean_pos_session(session, data)
        sale_completed = data.get('pos_sale_completed')
        result = {
            'cart': data.get('pos_cart', {}),
            'saleType': data.get('pos_sale_type'),
            'clientId': data.get('pos_client_id'),
            'clientName': data.get('pos_client_name'),
            'clientWallet': data.get('pos_client_wallet'),
            'saleStarted': data.get('pos_sale_started', False),
            'checkoutState': checkout_state,
        }
        if sale_completed:
            result['saleCompleted'] = sale_completed.get('message')
        return result
    except Session.DoesNotExist:
        return None


def cart_get(request):
    """Retrieve current cart from session.
    Supports ?sk=<session_key> to read another session's data (cross-browser).
    """
    if request.method == 'GET':
        sk = request.GET.get('sk')
        if sk:
            data = get_session_data(sk)
            if data is None:
                return JsonResponse({'error': 'Session not found'}, status=404)
            return JsonResponse(data)

        sale_started = request.session.get('pos_sale_started', False)
        checkout_state = request.session.get('pos_checkout_state')
        sale_completed = request.session.get('pos_sale_completed')

        # If saleCompleted is fresh, always suppress checkout state
        if sale_completed:
            elapsed = time.time() - sale_completed.get('timestamp', 0)
            if elapsed >= 6:
                del request.session['pos_sale_completed']
                sale_completed = None
                if 'pos_checkout_state' in request.session:
                    del request.session['pos_checkout_state']
                checkout_state = None
            elif checkout_state:
                del request.session['pos_checkout_state']
                checkout_state = None

        # Clear stale checkout state (active but no sale, no saleCompleted)
        if checkout_state and checkout_state.get('active') and not sale_started:
            del request.session['pos_checkout_state']
            checkout_state = None

        response_data = {
            'cart': request.session.get('pos_cart', {}),
            'saleType': request.session.get('pos_sale_type', 'menudeo'),
            'clientId': request.session.get('pos_client_id'),
            'clientName': request.session.get('pos_client_name'),
            'clientWallet': request.session.get('pos_client_wallet'),
            'saleStarted': sale_started,
            'checkoutState': checkout_state,
        }
        if sale_completed:
            response_data['saleCompleted'] = sale_completed.get('message')
        return JsonResponse(response_data)
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def checkout_save(request):
    """Save checkout state to session"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            request.session['pos_checkout_state'] = data
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def checkout_clear(request):
    """Clear checkout state from session"""
    if request.method == 'POST':
        try:
            if 'pos_checkout_state' in request.session:
                del request.session['pos_checkout_state']
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)


@csrf_exempt
def reset_display(request):
    """Clear all POS session data to reset the customer display."""
    if request.method == 'POST':
        keys = ['pos_cart', 'pos_client_id', 'pos_client_name',
                'pos_client_wallet', 'pos_sale_started', 'pos_checkout_state',
                'pos_sale_completed']
        for key in keys:
            if key in request.session:
                del request.session[key]
        request.session['pos_sale_type'] = 'menudeo'
        return JsonResponse({'success': True, 'message': 'Display reset'})
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required(login_url='/login/')
def customer_display(request):
    """Customer-facing ticket display page.
    Accepts ?sk=<session_key> to display cart from another browser's session.
    """
    sk = request.GET.get('sk')
    cart = {}
    sale_type = None
    client_name = None

    if sk:
        data = get_session_data(sk)
        if data:
            cart = data['cart']
            sale_type = data['saleType']
            client_name = data['clientName']
    else:
        cart = request.session.get('pos_cart', {})
        sale_type = request.session.get('pos_sale_type')
        client_name = request.session.get('pos_client_name')

    return render(request, 'pos/customer_display.html', {
        'title': 'Customer Display',
        'cart': cart,
        'sale_type': sale_type,
        'client_name': client_name,
        'sk': sk or '',
    })
