from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db.models import Q, Count

from im.models import ProductGroup, Product
from crm.decorators import role_required


@require_http_methods(["GET"])
@role_required('Admin', 'Manager', 'Buyer')
def group_list(request):
    groups = ProductGroup.objects.annotate(
        product_count=Count('products')
    ).order_by('name')

    context = {
        'title': 'Product Groups',
        'groups': groups,
    }
    return render(request, 'group/list.html', context)


@require_http_methods(["GET", "POST"])
@role_required('Admin', 'Manager', 'Buyer')
def group_edit(request, pk):
    group = get_object_or_404(ProductGroup, id=pk)
    products = group.products.filter(active=True).order_by('name')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        stockMin = request.POST.get('stockMin', 0)
        stockMax = request.POST.get('stockMax', 0)

        if not name:
            messages.error(request, 'Group name is required.')
        else:
            group.name = name
            group.stockMin = int(stockMin) if stockMin else 0
            group.stockMax = int(stockMax) if stockMax else 0
            group.save()
            messages.success(request, f'Group "{group.name}" updated.')

        return redirect('im:groupEdit', pk=pk)

    context = {
        'title': f'Edit Group: {group.name}',
        'group': group,
        'products': products,
    }
    return render(request, 'group/edit.html', context)


@require_http_methods(["POST"])
@role_required('Admin', 'Manager', 'Buyer')
def group_delete(request, pk):
    group = get_object_or_404(ProductGroup, id=pk)

    # Unlink all products from this group
    group.products.all().update(group=None)

    group_name = group.name
    group.delete()
    messages.success(request, f'Group "{group_name}" deleted.')
    return redirect('im:groupList')


@require_http_methods(["GET"])
@role_required('Admin', 'Manager', 'Buyer')
def group_product_search(request):
    q = request.GET.get('q', '').strip()
    group_id = request.GET.get('group_id')

    if len(q) < 1:
        return JsonResponse({'results': []})

    products = Product.objects.filter(active=True).filter(
        Q(clave__icontains=q) |
        Q(barcode__icontains=q) |
        Q(name__icontains=q)
    )

    if group_id:
        group = get_object_or_404(ProductGroup, id=group_id)
        already_in_group = group.products.values_list('id', flat=True)
        products = products.exclude(id__in=already_in_group)

    products = products[:30]

    results = []
    for p in products:
        label = p.name
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
            'name': p.name,
            'clave': p.clave or '',
            'barcode': p.barcode or '',
        })

    return JsonResponse({'results': results})


@require_http_methods(["POST"])
@role_required('Admin', 'Manager', 'Buyer')
def group_add_product(request, pk):
    group = get_object_or_404(ProductGroup, id=pk)
    product_id = request.POST.get('product_id')

    if not product_id:
        messages.error(request, 'No product specified.')
        return redirect('im:groupEdit', pk=pk)

    product = get_object_or_404(Product, id=product_id)
    product.group = group
    product.save()

    messages.success(request, f'"{product.name}" added to group "{group.name}".')
    return redirect('im:groupEdit', pk=pk)


@require_http_methods(["POST"])
@role_required('Admin', 'Manager', 'Buyer')
def group_remove_product(request, pk, product_id):
    group = get_object_or_404(ProductGroup, id=pk)
    product = get_object_or_404(Product, id=product_id)

    if product.group_id != group.id:
        messages.error(request, 'This product is not in this group.')
        return redirect('im:groupEdit', pk=pk)

    product.group = None
    product.save()

    messages.success(request, f'"{product.name}" removed from group "{group.name}".')
    return redirect('im:groupEdit', pk=pk)
