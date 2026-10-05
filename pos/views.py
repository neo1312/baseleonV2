import base64
import hmac
import json
import re
import time
import os
import unicodedata
from datetime import timedelta
from decimal import Decimal

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.conf import settings
from im.models import Product, DespieceConfig
from django.core.cache import cache
from django.db.models import Count, Q
from crm.models import Sale, saleItem, Client, Devolution, devolutionItem, Quote, quoteItem
from django.utils import timezone
from django.db import transaction
from crm.decorators import role_required
from pos.models import PrintJob
from pos import printing

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
        despiece_source_stock = dc.source_product.stock_ready_to_sale if dc else None
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
            'despiece_source_stock': despiece_source_stock,
            'despiece_units_per': float(dc.units_per_source) if dc else None,
        })
    return {
        'products': products_data,
        'clients': clients,
        'session_key': request.session.session_key,
    }

def _get_despiece_map():
    """Cached mapping of destination product id -> DespieceConfig (60s TTL).
    Cache is optional: if it's unavailable (e.g. no cache table), rebuild per call."""
    try:
        dc_map = cache.get('pos_despiece_map')
    except Exception:
        dc_map = None
    if dc_map is None:
        dc_map = {}
        for dc in DespieceConfig.objects.select_related('source_product').all():
            dc_map[dc.destination_product_id] = dc
        try:
            cache.set('pos_despiece_map', dc_map, 60)
        except Exception:
            pass
    return dc_map


def _get_despiece_source_stocks():
    """{source_product_id: ready-to-sale stock} for every despiece source (1 query)."""
    try:
        cached = cache.get('pos_despiece_src_stocks')
        if cached is not None:
            return cached
    except Exception:
        cached = None
    stocks = dict(
        Product.objects.filter(granel_conversion_as_source__isnull=False).annotate(
            s=Count('inventory_units', filter=Q(inventory_units__status='ready_to_sale'))
        ).values_list('id', 's')
    )
    try:
        cache.set('pos_despiece_src_stocks', stocks, 60)
    except Exception:
        pass
    return stocks


def _product_to_dict(p, stock=None, despiece_map=None, src_stocks=None):
    """Enrich a product with price, stock, and despiece info (search/scan shape)."""
    if despiece_map is None:
        despiece_map = _get_despiece_map()
    dc = despiece_map.get(p.id)
    granel_price = p.priceListaGranel if p.priceListaGranel != 'N/A' else None
    if dc:
        despiece_source_stock = (src_stocks.get(dc.source_product_id, 0)
                                 if src_stocks is not None
                                 else dc.source_product.stock_ready_to_sale)
    else:
        despiece_source_stock = None
    return {
        'id': p.id,
        'barcode': p.barcode,
        'clave': p.clave or '',
        'name': p.name,
        'brand': p.brand.name if p.brand else '',
        'compose_name': p.compose_name,
        'price': float(p.priceLista),
        'price_mayoreo': float(p.priceMayoreo),
        'price_granel': float(granel_price) if granel_price else None,
        'stock': stock if stock is not None else p.stock_ready_to_sale,
        'granel': p.granel,
        'Granel_Item': p.Granel_Item,
        'minimo': p.minimo,
        'despiece_config_id': dc.id if dc else None,
        'despiece_source_name': dc.source_product.compose_name if dc else None,
        'despiece_source_id': dc.source_product.id if dc else None,
        'despiece_source_stock': dc.source_product.stock_ready_to_sale if dc else None,
        'despiece_units_per': float(dc.units_per_source) if dc else None,
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
def pos_landing(request):
    """Landing/rest page with Ferre León branding"""
    return render(request, 'pos/landing.html', {'title': 'Inicio'})

@login_required(login_url='/login/')
def pos_index_touch(request):
    """Touch-optimized POS interface for 10-inch tablets"""
    context = {
        'title': 'POS - Touch',
        **_get_pos_context(request),
    }
    return render(request, 'pos/index_touch.html', context)

def _norm_text(s):
    """Normalize text for search: lowercase + strip accents."""
    return unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode('ascii').lower()


def _query_words(q):
    """Split a search query into normalized words (separated by non-alphanumeric chars)."""
    return [w for w in re.split(r'[^a-z0-9]+', _norm_text(q)) if w]


def _product_tokens(p):
    """Normalized tokens (words) of compose_name (name + brand)."""
    return [w for w in re.split(r'[^a-z0-9]+', _norm_text(p.compose_name)) if w]


def _match_score(tokens, words):
    """Total score if every word matches a token (exact=3, prefix=2, contains=1).
    Returns None if any word is missing."""
    total = 0
    for word in words:
        best = 0
        for tok in tokens:
            if tok == word:
                best = 3
                break
            if tok.startswith(word):
                if best < 2:
                    best = 2
            elif best == 0 and word in tok:
                best = 1
        if best == 0:
            return None
        total += best
    return total


@csrf_exempt
def search_products(request):
    """Search products.
    - Single word  -> exact barcode/clave only (no fuzzy, no description fallback).
    - 2+ words     -> description over compose_name (name + brand): all words
      required (AND), ranked exact(3) > prefix(2) > contains(1); in-stock
      first, out-of-stock at the end.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse([], safe=False)

    words = _query_words(query)

    if len(words) <= 1:
        qs = Product.objects.filter(active=True).filter(
            Q(barcode__iexact=query) | Q(clave__iexact=query)
        ).select_related('brand').annotate(
            stock_annot=Count('inventory_units', filter=Q(inventory_units__status='ready_to_sale'))
        )[:20]
        despiece_map = _get_despiece_map()
        src_stocks = _get_despiece_source_stocks()
        results = [_product_to_dict(p, stock=p.stock_annot, despiece_map=despiece_map, src_stocks=src_stocks) for p in qs]
        return JsonResponse(results, safe=False)

    qs = Product.objects.filter(active=True).select_related('brand').annotate(
        stock_annot=Count('inventory_units', filter=Q(inventory_units__status='ready_to_sale'))
    )
    scored = []
    for p in qs:
        score = _match_score(_product_tokens(p), words)
        if score is not None:
            scored.append((score, p.stock_annot, p.id, p))
    scored.sort(key=lambda x: (0 if x[1] > 0 else 1, -x[0], -x[1], x[2]))
    despiece_map = _get_despiece_map()
    src_stocks = _get_despiece_source_stocks()
    results = [_product_to_dict(p, stock=p.stock_annot, despiece_map=despiece_map, src_stocks=src_stocks) for _, _, _, p in scored[:50]]
    return JsonResponse(results, safe=False)


@csrf_exempt
def search_index(request):
    """Compact catalog of active products for client-side instant search."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    qs = Product.objects.filter(active=True).select_related('brand').annotate(
        stock_annot=Count('inventory_units', filter=Q(inventory_units__status='ready_to_sale'))
    )
    despiece_map = _get_despiece_map()
    src_stocks = _get_despiece_source_stocks()
    results = [_product_to_dict(p, stock=p.stock_annot, despiece_map=despiece_map, src_stocks=src_stocks) for p in qs]
    return JsonResponse(results, safe=False)


@csrf_exempt
def search_stock(request):
    """Lightweight {id: stock} map for refreshing the client index."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    qs = Product.objects.filter(active=True).annotate(
        s=Count('inventory_units', filter=Q(inventory_units__status='ready_to_sale'))
    ).values_list('id', 's')
    return JsonResponse(dict(qs))

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
        
        return JsonResponse(_product_to_dict(product))
    
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
    """Get single product details (enriched: price, stock, despiece info)"""
    if request.method == 'GET':
        product_id = request.GET.get('id')
        
        try:
            product = Product.objects.get(id=product_id)
            return JsonResponse(_product_to_dict(product))
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def get_sale_for_return(request, sale_id):
    """Return original sale data for processing a return."""
    try:
        sale = Sale.objects.get(id=sale_id, status='completed')
        items = []
        for si in sale.saleitem_set.all():
            items.append({
                'product_id': si.product.id if si.product else None,
                'name': si.product.compose_name if si.product else 'Deleted Product',
                'barcode': si.product.barcode if si.product else '',
                'quantity': int(float(si.quantity)),
                'price': float(si.price),
                'item_total': float(si.price * Decimal(str(si.quantity))),
                'sat': si.sat,
                'sale_item_id': si.id,
            })
        return JsonResponse({
            'sale_id': sale.id,
            'client': sale.client.name if sale.client else 'Público en general',
            'client_id': sale.client.id if sale.client else None,
            'tipo': sale.tipo,
            'payment_method': sale.payment_method,
            'date': sale.date_created,
            'items': items,
            'total': float(sale.total_amount),
        })
    except Sale.DoesNotExist:
        return JsonResponse({'error': 'Sale not found'}, status=404)


@csrf_exempt
@transaction.atomic
def complete_sale(request):
    """Complete a sale, devolution, or quote based on mode."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            mode = data.get('mode', 'sale')
            items = data.get('items', [])
            if not items:
                return JsonResponse({'error': 'No items in cart'}, status=400)
            
            client_id = data.get('client_id')
            
            # Get or create client
            if client_id:
                client = Client.objects.get(id=client_id)
            else:
                client, _ = Client.objects.get_or_create(
                    name='mostrador',
                    defaults={'phoneNumber': '0000', 'tipo': 'menudeo'}
                )
            
            tipo = data.get('tipo', 'menudeo')
            total_quantity = 0
            total_amount = Decimal('0')
            
            if mode == 'devolucion':
                # Process return: create Devolution + devolutionItems
                original_sale_id = data.get('original_sale_id')
                devolution = Devolution.objects.create(
                    client=client,
                    tipo=tipo,
                    date_created=timezone.now(),
                )
                
                for item_data in items:
                    product = Product.objects.get(id=item_data['product_id'])
                    quantity = int(item_data['quantity'])
                    sale_item_id = item_data.get('sale_item_id')
                    
                    price = Decimal(str(item_data.get('price', 0)))

                    d_item = devolutionItem.objects.create(
                        product=product,
                        devolution=devolution,
                        quantity=quantity,
                        cost=str(price),
                        margen='0',
                        sale_item_id=sale_item_id,
                        purchase_with_iva=item_data.get('sat', False),
                    )
                    
                    item_total = price * Decimal(str(quantity))
                    total_amount += item_total
                    total_quantity += quantity
                
                devolution.save()
                
                return JsonResponse({
                    'success': True,
                    'sale_id': devolution.id,
                    'message': f'Devolución #{devolution.id} completada',
                    'total': float(total_amount),
                })
            
            elif mode == 'cotizacion':
                # Process quote: create Quote + quoteItems (no inventory change)
                quote = Quote.objects.create(
                    client=client,
                    tipo=tipo,
                    date_created=timezone.now(),
                )
                
                for item_data in items:
                    product = Product.objects.get(id=item_data['product_id'])
                    quantity = int(item_data['quantity'])
                    
                    if tipo == 'mayoreo':
                        price = Decimal(str(product.priceMayoreo))
                    else:
                        if product.granel and quantity < int(product.minimo):
                            granel_price = product.priceListaGranel
                            price = Decimal(str(granel_price)) if granel_price != 'N/A' else Decimal(str(product.priceLista))
                        else:
                            price = Decimal(str(product.priceLista))
                    
                    q_item = quoteItem.objects.create(
                        product=product,
                        quote=quote,
                        quantity=quantity,
                        cost=str(price),
                        margen='0',
                    )
                    
                    item_total = price * Decimal(str(quantity))
                    total_amount += item_total
                    total_quantity += quantity
                
                quote.save()
                
                return JsonResponse({
                    'success': True,
                    'sale_id': quote.id,
                    'message': f'Cotización #{quote.id} completada',
                    'total': float(total_amount),
                })
            
            else:  # mode == 'sale' (default)
                payment_method = data.get('payment_method', 'cash')
                wallet_discount = Decimal(str(data.get('wallet_discount', 0)))
                
                sale = Sale.objects.create(
                    client=client,
                    payment_method=payment_method,
                    tipo=tipo,
                    date_created=timezone.now(),
                    status='completed',
                )
                
                for item_data in items:
                    product = Product.objects.get(id=item_data['product_id'])
                    quantity = int(item_data['quantity'])
                    
                    if tipo == 'mayoreo':
                        price = Decimal(str(product.priceMayoreo))
                    else:
                        if product.granel and quantity < int(product.minimo):
                            granel_price = product.priceListaGranel
                            price = Decimal(str(granel_price)) if granel_price != 'N/A' else Decimal(str(product.priceLista))
                        else:
                            price = Decimal(str(product.priceLista))
                    
                    if product.stock_ready_to_sale < quantity:
                        raise ValueError(f"Insufficient stock for {product.compose_name}")
                    
                    sale_item = saleItem.objects.create(
                        sale=sale,
                        product=product,
                        quantity=quantity,
                        price=price,
                        sat=product.sat,
                    )
                    
                    item_total = price * Decimal(str(quantity))
                    total_amount += item_total
                    total_quantity += quantity
                
                if wallet_discount > 0 and client_id:
                    if hasattr(client, 'monedero'):
                        client.monedero = Decimal(str(client.monedero or 0)) - wallet_discount
                        client.save()
                    total_amount -= wallet_discount
                
                sale.total_items = total_quantity
                sale.total_amount = total_amount
                sale.save()
                
                return JsonResponse({
                    'success': True,
                    'sale_id': sale.id,
                    'message': f'Venta #{sale.id} completada',
                    'total': float(total_amount),
                })
            
        except Product.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


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


SCANNER_FILE = os.path.join(getattr(settings, 'BASE_DIR', '/tmp'), '.scanner_barcode')

SCANNER_LAST = {'barcode': '', 'ts': 0}

@csrf_exempt
def scanner_push(request):
    """Receive barcode from scanner server via HTTP POST (cross-network fallback)."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            barcode = data.get('barcode')
            if barcode:
                now = time.time()
                if barcode == SCANNER_LAST['barcode'] and (now - SCANNER_LAST['ts']) < 2:
                    return JsonResponse({'ok': True, 'dup': True})
                SCANNER_LAST['barcode'] = barcode
                SCANNER_LAST['ts'] = now
                with open(SCANNER_FILE, 'w') as f:
                    json.dump({'barcode': barcode, 'ts': now}, f)
                return JsonResponse({'ok': True})
        except (json.JSONDecodeError, AttributeError, OSError):
            pass
    return JsonResponse({'ok': False}, status=400)

def scanner_poll(request):
    """Return pending scanner barcode (file-based, works across all workers)."""
    try:
        with open(SCANNER_FILE) as f:
            data = json.load(f)
        if time.time() - data.get('ts', 0) < 30:
            try:
                os.remove(SCANNER_FILE)
            except OSError:
                pass
            return JsonResponse({'barcode': data.get('barcode')})
    except (OSError, json.JSONDecodeError):
        pass
    return JsonResponse({'barcode': None})


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

# ─── Print queue (tablet Bluetooth bridge) ─────────────────────────

def _print_token_ok(request):
    required = getattr(settings, 'PRINT_API_TOKEN', '') or ''
    if not required:
        return True
    supplied = request.headers.get('X-Print-Token', '') or ''
    return hmac.compare_digest(supplied, required)


def _ticket_json_for(ticket_type, pk):
    """Same shape as the crm *_ticket_json endpoints, for server-side formatting."""
    if ticket_type == 'sale':
        obj = Sale.objects.get(id=pk)
        items = obj.saleitem_set.all()
        return {
            'sale_id': obj.id,
            'total': float(obj.total_amount),
            'client': obj.client.name if obj.client else 'Público en general',
            'date': obj.date_created,
            'items': [
                {
                    'name': i.product.compose_name if i.product else 'Deleted Product',
                    'price': float(i.price),
                    'quantity': float(i.quantity),
                    'item_total': float(i.price) * float(i.quantity),
                }
                for i in items
            ],
        }
    if ticket_type == 'quote':
        obj = Quote.objects.get(id=pk)
        items = obj.quoteitem_set.all()
        return {
            'sale_id': obj.id,
            'total': float(obj.get_cart_total),
            'client': obj.client.name if obj.client else 'Público en general',
            'date': obj.date_created,
            'items': [
                {
                    'name': i.product.compose_name if i.product else 'Deleted Product',
                    'price': float(i.precioUnitario),
                    'quantity': float(i.quantity),
                    'item_total': float(i.get_total),
                }
                for i in items
            ],
        }
    if ticket_type == 'devolution':
        obj = Devolution.objects.get(id=pk)
        items = obj.devolutionitem_set.all()
        return {
            'sale_id': obj.id,
            'total': float(obj.get_cart_total),
            'client': obj.client.name if obj.client else 'Público en general',
            'date': obj.date_created,
            'items': [
                {
                    'name': i.product.compose_name if i.product else 'Deleted Product',
                    'price': float(i.precioUnitario),
                    'quantity': float(i.quantity),
                    'item_total': float(i.get_total),
                }
                for i in items
            ],
        }
    raise ValueError('invalid ticket_type')


def _serialize_job(job):
    """Return (filename, base64 ESC/POS bytes) for a job."""
    if job.job_type == PrintJob.JOB_TICKET:
        data = _ticket_json_for(job.ticket_type, job.ref_id)
        raw = printing.build_ticket_bytes(data, job.ticket_type)
        filename = 'ticket_{}_{}.bin'.format(job.ticket_type, job.ref_id)
    else:
        raw = printing.build_label_bytes(job.value, job.copies, job.blank)
        filename = 'label_{}.bin'.format(job.value or 'blank')
    return filename, base64.b64encode(raw).decode('ascii')


@csrf_exempt
def create_print_job(request):
    """Queue a ticket or label. Called by the browser (same-origin)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    try:
        data = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    job_type = data.get('job_type') or ('ticket' if data.get('sale_id') else 'label')
    try:
        if job_type == PrintJob.JOB_TICKET:
            sale_id = data.get('sale_id')
            ticket_type = data.get('ticket_type', 'sale')
            if sale_id in (None, ''):
                return JsonResponse({'error': 'sale_id required'}, status=400)
            if ticket_type not in printing.TICKET_LABELS:
                return JsonResponse({'error': 'invalid ticket_type'}, status=400)
            job = PrintJob.objects.create(
                job_type=PrintJob.JOB_TICKET,
                ticket_type=ticket_type,
                ref_id=int(sale_id),
            )
        elif job_type == PrintJob.JOB_LABEL:
            value = str(data.get('value', '')).strip()
            blank = bool(data.get('blank', False))
            if not value and not blank:
                return JsonResponse({'error': 'value required'}, status=400)
            copies = int(data.get('copies', 1) or 1)
            job = PrintJob.objects.create(
                job_type=PrintJob.JOB_LABEL,
                value=value,
                copies=max(1, copies),
                blank=blank,
            )
        else:
            return JsonResponse({'error': 'invalid job_type'}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'invalid payload'}, status=400)

    return JsonResponse({'success': True, 'job_id': job.id})


@csrf_exempt
def pending_print_jobs(request):
    """Atomically claim pending jobs and return them with ESC/POS bytes."""
    if not _print_token_ok(request):
        return JsonResponse({'error': 'unauthorized'}, status=401)
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid method'}, status=405)

    ttl = getattr(settings, 'PRINT_TTL_SECONDS', 300)
    cutoff = timezone.now() - timedelta(seconds=ttl)
    with transaction.atomic():
        PrintJob.objects.filter(
            status=PrintJob.STATUS_PENDING, created_at__lt=cutoff
        ).update(status=PrintJob.STATUS_FAILED, error='expired')
        jobs = list(
            PrintJob.objects.select_for_update()
            .filter(status=PrintJob.STATUS_PENDING)
            .order_by('created_at')[:10]
        )
        now = timezone.now()
        for job in jobs:
            job.status = PrintJob.STATUS_PROCESSING
            job.claimed_at = now
            job.save(update_fields=['status', 'claimed_at', 'updated_at'])

    result = []
    for job in jobs:
        try:
            filename, data_b64 = _serialize_job(job)
        except Exception as e:
            job.status = PrintJob.STATUS_FAILED
            job.error = str(e)
            job.save(update_fields=['status', 'error', 'updated_at'])
            continue
        result.append({
            'job_id': job.id,
            'job_type': job.job_type,
            'ticket_type': job.ticket_type,
            'filename': filename,
            'data_b64': data_b64,
        })
    return JsonResponse(result, safe=False)


@csrf_exempt
def print_job_bytes(request, job_id):
    """Return ESC/POS bytes for a single job (optional direct fetch)."""
    if not _print_token_ok(request):
        return JsonResponse({'error': 'unauthorized'}, status=401)
    try:
        job = PrintJob.objects.get(id=job_id)
    except PrintJob.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)
    try:
        filename, data_b64 = _serialize_job(job)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'filename': filename, 'data_b64': data_b64})


@csrf_exempt
def ack_print_job(request, job_id):
    if not _print_token_ok(request):
        return JsonResponse({'error': 'unauthorized'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    PrintJob.objects.filter(id=job_id).update(status=PrintJob.STATUS_DONE)
    return JsonResponse({'success': True})


@csrf_exempt
def fail_print_job(request, job_id):
    if not _print_token_ok(request):
        return JsonResponse({'error': 'unauthorized'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    error = ''
    retry = False
    try:
        data = json.loads(request.body or '{}')
        error = str(data.get('error', ''))[:1000]
        retry = bool(data.get('retry', False))
    except (ValueError, TypeError):
        pass
    status = PrintJob.STATUS_PENDING if retry else PrintJob.STATUS_FAILED
    PrintJob.objects.filter(id=job_id).update(status=status, error=error)
    return JsonResponse({'success': True, 'status': status})


def label_page(request):
    """Page to queue barcode labels (same 58mm printer)."""
    return render(request, 'pos/label.html', {
        'store_name': getattr(settings, 'STORE_NAME', 'Ferreteria Leon'),
    })



