import json
from decimal import Decimal
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from im.models import Product
from crm.models import Sale, saleItem, Client
from django.utils import timezone
from django.db import transaction
from crm.decorators import role_required

@login_required(login_url='/login/')
def pos_index(request):
    """Main POS interface"""
    # NOTE: Using stock_ready_to_sale (from InventoryUnit) as single source of truth
    # Product.stock field has been removed - use stock_ready_to_sale property instead
    
    # Get all active products
    all_products = list(Product.objects.filter(active=True)[:100])
    
    # Filter to only products with available stock (ready_to_sale InventoryUnits)
    # and sort by availability
    products = [
        p for p in all_products 
        if p.stock_ready_to_sale > 0
    ]
    products.sort(key=lambda p: p.stock_ready_to_sale, reverse=True)
    
    # Get all clients
    clients = Client.objects.all()[:100]
    
    # Enrich products with price data - USE STOCK_READY_TO_SALE (correct field)
    products_data = []
    for p in products:
        granel_price = p.priceListaGranel if p.priceListaGranel != 'N/A' else None
        # USE stock_ready_to_sale - the ONLY correct source of inventory truth
        available_stock = p.stock_ready_to_sale
        
        products_data.append({
            'id': p.id,
            'barcode': p.barcode,
            'name': p.name,
            'price': float(p.priceLista),
            'price_mayoreo': float(p.priceMayoreo),
            'price_granel': float(granel_price) if granel_price else None,
            'stock': available_stock,
            'unidadEmpaque': p.unidadEmpaque,
            'granel': p.granel,
            'minimo': p.minimo,
        })
    
    context = {
        'title': 'POS - Point of Sale',
        'products': products_data,
        'clients': clients,
    }
    return render(request, 'pos/index.html', context)

@csrf_exempt
def search_products(request):
    """Search products by name, SKU, or barcode"""
    if request.method == 'GET':
        query = request.GET.get('q', '').strip()
        
        # Get all active products
        if not query:
            products = Product.objects.filter(active=True)[:50]
        else:
            # Search by name, SKU, or barcode
            products = Product.objects.filter(
                active=True
            ).filter(
                models.Q(name__icontains=query) |
                models.Q(barcode__icontains=query)
            )[:50]
        
        # Filter to only products with available stock and sort by availability
        products_list = [
            p for p in products 
            if p.stock_ready_to_sale > 0
        ]
        products_list.sort(key=lambda p: p.stock_ready_to_sale, reverse=True)
        
        # Enrich with price data - USE STOCK_READY_TO_SALE (only source of truth)
        results = []
        for p in products_list:
            granel_price = p.priceListaGranel if p.priceListaGranel != 'N/A' else None
            available_stock = p.stock_ready_to_sale
            
            results.append({
                'id': p.id,
                'barcode': p.barcode,
                'name': p.name,
                'price': float(p.priceLista),
                'price_mayoreo': float(p.priceMayoreo),
                'price_granel': float(granel_price) if granel_price else None,
                'stock': available_stock,
                'granel': p.granel,
                'minimo': p.minimo,
            })
        
        return JsonResponse(results, safe=False)
    
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
            # USE stock_ready_to_sale - the ACTUAL available inventory
            available_stock = product.stock_ready_to_sale
            
            return JsonResponse({
                'id': product.id,
                'name': product.name,
                'stock': available_stock,  # NOW CORRECT - from InventoryUnit
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
                    # USE stock_ready_to_sale - the ACTUAL available inventory
                    available = product.stock_ready_to_sale
                    is_valid = available >= requested_qty
                    
                    validation_results.append({
                        'product_id': product_id,
                        'product_name': product.name,
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
                'price': float(price),
                'price_granel': float(granel_price) if granel_price else None,
                'stock': product.stock_ready_to_sale,  # USE CORRECT FIELD
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
            total_amount = Decimal(str(data.get('total_amount', 0)))
            
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
            
            # Add items to sale
            total_quantity = 0
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
                
                # Validate stock - USE stock_ready_to_sale (InventoryUnit ready_to_sale count)
                if product.stock_ready_to_sale < quantity:
                    raise ValueError(f"Insufficient stock for {product.name}")
                
                # Create sale item
                sale_item = saleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=quantity,
                    price=price,
                )
                
                # NOTE: InventoryUnit signal handlers automatically manage inventory status changes
                # When saleItem is created, signals mark InventoryUnit records as 'sold'
                # Product.stock_ready_to_sale count decreases automatically
                
                # Calculate item total (price * quantity)
                total_quantity += quantity
            
            # Handle wallet discount if applied
            if wallet_discount > 0 and client_id:
                # Deduct from client's wallet
                if hasattr(client, 'monedero'):
                    client.monedero = Decimal(str(client.monedero or 0)) - wallet_discount
                    client.save()
            
            # Update sale totals
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
