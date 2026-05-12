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
    # Get all products with stock
    products = list(Product.objects.filter(
        stock__gt=0
    ).order_by('-stock')[:50])
    
    # Enrich products with price data
    products_data = []
    for p in products:
        products_data.append({
            'id': p.id,
            'barcode': p.barcode,
            'name': p.name,
            'price': float(p.priceLista),
            'price_mayoreo': float(p.priceMayoreo),
            'stock': p.stock,
            'unidadEmpaque': p.unidadEmpaque,
            'granel': p.granel,
            'minimo': p.minimo,
        })
    
    context = {
        'title': 'POS - Point of Sale',
        'products': products_data,
    }
    return render(request, 'pos/index.html', context)

@csrf_exempt
def search_products(request):
    """Search products by name, SKU, or barcode"""
    if request.method == 'GET':
        query = request.GET.get('q', '').strip()
        
        if not query:
            products = Product.objects.filter(
                stock__gt=0
            ).order_by('-stock')[:20]
        else:
            # Search by name, SKU, or barcode
            products = Product.objects.filter(
                stock__gt=0
            ).filter(
                models.Q(name__icontains=query) |
                models.Q(barcode__icontains=query)
            ).order_by('-stock')[:20]
        
        # Enrich with price data
        results = []
        for p in products:
            results.append({
                'id': p.id,
                'barcode': p.barcode,
                'name': p.name,
                'price': float(p.priceLista),
                'price_mayoreo': float(p.priceMayoreo),
                'stock': p.stock,
                'granel': p.granel,
                'minimo': p.minimo,
            })
        
        return JsonResponse(results, safe=False)
    
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
            
            return JsonResponse({
                'id': product.id,
                'barcode': product.barcode,
                'name': product.name,
                'price': float(price),
                'stock': product.stock,
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
            
            # Get or create client
            if client_id:
                client = Client.objects.get(id=client_id)
            else:
                # Use default "General" client
                client, _ = Client.objects.get_or_create(
                    name='General',
                    defaults={'email': 'general@store.com'}
                )
            
            # Create sale
            total_amount = Decimal('0')
            total_quantity = 0
            tipo = data.get('tipo', 'menudeo')  # menudeo or mayoreo
            
            sale = Sale.objects.create(
                client=client,
                payment_method=payment_method,
                tipo=tipo,
                date_created=timezone.now(),
                status='completed',
            )
            
            # Add items to sale
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
                
                # Validate stock
                if product.stock < quantity:
                    raise ValueError(f"Insufficient stock for {product.name}")
                
                # Create sale item
                sale_item = saleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=quantity,
                    price=price,
                )
                
                # Update product stock
                product.stock -= quantity
                product.save()
                
                # Calculate item total (price * quantity)
                item_total = price * quantity
                total_amount += item_total
                total_quantity += quantity
            
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
