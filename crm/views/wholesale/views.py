from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from im.models import Product
from django.db import models


@login_required(login_url='/login/')
def lookup_page(request):
    return render(request, 'wholesale/lookup.html', {
        'title': 'Consultar Productos',
    })


@csrf_exempt
@login_required(login_url='/login/')
def search_products(request):
    if request.method == 'GET':
        query = request.GET.get('q', '').strip()

        if not query:
            products = Product.objects.filter(active=True)[:30]
        else:
            words = query.split()
            filters = models.Q()
            for word in words:
                filters &= models.Q(name__icontains=word)
            filters |= models.Q(barcode__icontains=query)
            filters |= models.Q(clave__icontains=query)
            filters |= models.Q(brand__name__icontains=query)
            products = Product.objects.filter(active=True).filter(filters)[:50]

        results = []
        for p in products:
            stock = p.stock_ready_to_sale
            granel_price = p.priceListaGranel if p.priceListaGranel != 'N/A' else None

            results.append({
                'id': p.id,
                'clave': p.clave or '',
                'barcode': p.barcode,
                'name': p.name,
                'brand': p.brand.name if p.brand else '',
                'category': p.category.name if p.category else '',
                'price': float(p.priceLista),
                'price_mayoreo': float(p.priceMayoreo),
                'granel': p.granel,
                'Granel_Item': p.Granel_Item,
                'minimo': p.minimo,
                'granel_price': float(granel_price) if granel_price else None,
                'stock': stock,
                'unidad': p.unidad,
            })

        return JsonResponse(results, safe=False)

    return JsonResponse({'error': 'Invalid request'}, status=400)
