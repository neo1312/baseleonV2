#basic libraries

from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse,HttpResponse
import json
from django.template.loader import get_template
from xhtml2pdf import pisa
import csv, io
from django.views.decorators.csrf import csrf_exempt

#import 
from scm.models import Purchase,Provider,Product,purchaseItem
from scm.forms import purchaseForm 
from io import TextIOWrapper
from django.urls import reverse
from django.db import IntegrityError, transaction
from django.utils import timezone
from crm.decorators import role_required


@csrf_exempt
@role_required('Admin', 'Buyer')
def purchaseInicia(request):
    if request.method == "POST":
        provider=Provider.objects.get(name='general')
        purchase=Purchase.objects.create(provider=provider)
        purchase.save()
    return JsonResponse('Compra Registrada',safe=False)

@role_required('Admin', 'Buyer', 'Manager')
def purchaseList(request):
    data = {
            'purchase_create':'/purchase/create',
            'title' : 'Listado purchases',
            'purchases' : Purchase.objects.all(),
            'entity':'Crear compra',
            'url_create':'/purchase/create',
            'url_js':'/static/lib/java/purchase/list.js',
            'btnId':'btnOrderList',
            'entityUrl':'/purchase/new',
            'home':'home'
            }
    return render(request, 'purchase/list.html', data)

def purchaseEdit(request,pk):

    purchase=get_object_or_404(Purchase,id=pk)
    if request.method != 'POST':
        form=purchaseForm(instance=purchase)
    else:
        form = purchaseForm(request.POST,instance=purchase)
        if form.is_valid():
            form.save()
            return redirect ( '/purchase/list')
    context={
            'form':form,
            'title' : 'purchase Edit',
            'entity':'purchasees',
            'retornoLista':'/purchase/list',
            } 
    return render(request, 'purchase/edit.html',context) 

def purchaseDelete(request,pk):
    purchase=Purchase.objects.get(id=pk)
    if request.method == 'POST':
        purchase.delete()
        return redirect ( '/purchase/list')

    context = {
            'item':purchase,
            'title' : 'purchase Delete',
            'entity':'purchasees',
            'retornoLista':'/purchase/list',
            }
    return render(request,  'purchase/delete.html',context)

def purchaseCreate(request):
    purchase = get_latest_purchase()
    items = purchase.purchaseitem_set.all() if purchase else []
    context={
            'url_js':'/static/lib/java/purchase/create.js',
            'items':items,
            'total':purchase,
            'returnCreate':'/purchase/new'
            }
    return render(request, 'purchase/create.html',context)

@csrf_exempt
def purchaseGetData(request):
    if request.method == 'POST':
        call= json.loads(request.body)
        pk=call['id']
        pk1=str(pk)
        qs=Product.objects.get(pv1=pk)
        name = [qs.id,qs.name,qs.costo]
        return JsonResponse({'datos':name},safe=False)

def purchaseItemView(request):
    if request.method == "POST":
        data = json.loads(request.body)
        purchase = get_latest_purchase()
        if purchase is None:
            provider = Provider.objects.filter(name='general').first() or Provider.objects.first()
            if provider is None:
                return JsonResponse('No provider available for purchase.', safe=False, status=400)
            purchase = Purchase.objects.create(provider=provider)
        pk=int(data[0])
        quantity=int(data[1])
        product=Product.objects.get(id=pk)
        costo=product.costo
        
        itemspurchase=purchase.purchaseitem_set.all()
        outputlist=list(filter(lambda x:x.product.id==pk,itemspurchase))
        if outputlist:
            repetido=outputlist[0]
            # Update quantity in place instead of delete/recreate
            new_quantity=int(repetido.quantity)+quantity
            repetido.quantity = new_quantity
            repetido.save()
            return JsonResponse({'status': 'updated', 'message': 'se sumaron', 'item_id': repetido.id, 'quantity': new_quantity, 'total': float(repetido.get_total)}, safe=False)
        else:
            new_item = purchaseItem.objects.create(product=product,purchase=purchase,quantity=quantity,cost=costo)
            return JsonResponse({'status': 'created', 'message': 'creo nuevo registro', 'item_id': new_item.id, 'quantity': quantity, 'total': float(new_item.get_total)}, safe=False)


def purchaseItemDelete(request,pk):
    item=purchaseItem.objects.get(id=pk)
    if request.method == 'POST':
        item.delete()
        return redirect ( '/purchase/create')
    context = {
            'item':item,
            'title' : 'item Delete',
            'entity':'orders',
            'retornoLista':'/purchase/list',
            }
    return render(request,  'purchase/delete.html',context)

@csrf_exempt
def purchaseUpdateQuantity(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            item_id = data.get('item_id')
            quantity = int(data.get('quantity', 1))
            
            if quantity < 1:
                return JsonResponse({'status': 'error', 'message': 'Quantity must be at least 1'}, status=400)
            
            item = purchaseItem.objects.get(id=item_id)
            item.quantity = quantity
            item.save()
            
            return JsonResponse({
                'status': 'success',
                'quantity': item.quantity,
                'cost': float(item.cost),
                'total': float(item.get_total)
            })
        except purchaseItem.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Item not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


def purchaseOrder(request, pk):
    try:
        provider = Provider.objects.get(id=pk)
    except Provider.DoesNotExist:
        provider = None
    
    # Get products that have a ProductProvider entry for this provider
    from im.models import ProductProvider
    if provider:
        product_ids = ProductProvider.objects.filter(provider=provider).values_list('product_id', flat=True)
        query = Product.objects.filter(id__in=product_ids)
    else:
        query = Product.objects.none()
    
    product = list(filter(lambda x: x.faltante1 != 'no', query))
    productFaltante = filter(lambda x: x.faltante1 != 0, product)

    response = HttpResponse(content_type='text/csv')
    writer = csv.writer(response)
    writer.writerow(['cantidad', 'Clave', 'Descripcion', 'Empaque','Total','id','product', 'purchase','quantity','cost','date_created','last_update'])

    seen_barcodes = set()  # Track unique products by SKU
    seen_groups = set()

    for p in productFaltante:
        if p.group and p.group.id in seen_groups:
            continue
        if p.group:
            seen_groups.add(p.group.id)
        pv1 = p.get_pv1(provider)
        # Skip if we've already added this product based on SKU
        if pv1 in seen_barcodes:
            continue
        seen_barcodes.add(pv1)

        writer.writerow([
            p.faltante1,
            pv1,              # Barcode / Provider Key
            p.full_name,
            1,
            float(p.costo),
            " ",
            p.id,
            " ",
            float(p.faltante1),
            p.costo,
            " ",
            " "
        ])

    response['Content-Disposition'] = 'attachment; filename="prodctCost.csv"'
    return response



def purchaseNew(request):
    # Get filter parameters
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    
    purchases = []
    show_list = False
    
    # Only query purchases if at least one filter is applied
    if date_from or date_to:
        purchases = Purchase.objects.all().order_by('-date_created')
        show_list = True
        
        # Parse dates carefully
        try:
            if date_from:
                from datetime import datetime
                dt_from = datetime.strptime(date_from, '%Y-%m-%d')
                purchases = purchases.filter(date_created__gte=dt_from)
        except (ValueError, TypeError):
            pass
        
        try:
            if date_to:
                from datetime import datetime
                dt_to = datetime.strptime(date_to, '%Y-%m-%d')
                # Add 1 day to include the entire day
                from datetime import timedelta
                dt_to = dt_to + timedelta(days=1)
                purchases = purchases.filter(date_created__lt=dt_to)
        except (ValueError, TypeError):
            pass
    
    data = {
        'purchase_create':'/purchase/create',
        'title' : 'Alta de Compra',
        'entity':'Lista de Compras',
        'url_create':'/purchase/create',
        'url_js':'/static/lib/java/purchase/list.js',
        'btnId':'btnOrderList',
        'entityUrl':'/purchase/list',
        'home':'home',
        'newBtn':'Compra',
        'purchases': purchases,
        'show_list': show_list,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'purchase/new.html', data)

def upload_purchase_items(request):
    if request.method == "POST" and request.FILES.get("csv_file"):
        csv_file = request.FILES["csv_file"]
        data = []
        headers = []

        # Read CSV
        csv_reader = csv.reader(TextIOWrapper(csv_file.file, encoding="utf-8"))
        headers = next(csv_reader)
        for row in csv_reader:
            data.append(row)

        # Render CSV preview table
        html = render_to_string("purchase/csv_table.html", {
            "headers": headers,
            "data": data
        })
        return HttpResponse(html)

    # First time load
    return render(request, "purchase/create.html")


def htmx_one(request):
    return HttpResponse("<p>Hello from the server!</p>")

def htmx_form(request):
    name = request.POST.get('name','Anonymous')
    return HttpResponse(f"<p>Hello, {name}! This came form HMTX form.</p>")

def upload_csv(request):
    return render(request, "purchase/upload_purchase_items.html")



# ------------------------------
# Helper para fechas del CSV
# ------------------------------
def parse_datetime_or_now(value):
    """
    Convierte valores vacíos a timezone.now().
    Si la fecha viene en string válido, Django la convierte.
    """
    if value is None:
        return timezone.now()
    
    value = str(value).strip()
    if value == "":
        return timezone.now()
    
    return value  # Django intentará convertirlo


def get_first_csv_value(row, *keys):
    for key in keys:
        value = row.get(key)
        if value is None:
            continue

        value = str(value).strip()
        if value != "":
            return value

    return None


def normalize_csv_key(value):
    if value is None:
        return None
    return str(value).replace('\ufeff', '').replace('ï»¿', '').strip()


def get_latest_purchase():
    return Purchase.objects.order_by('-id').first()


def resolve_csv_product(row):
    product_id_value = get_first_csv_value(row, 'product', 'product_id')
    if product_id_value:
        try:
            product = Product.objects.filter(id=int(product_id_value)).first()
            if product:
                return product
        except (ValueError, TypeError):
            pass

    pv1_value = get_first_csv_value(row, 'pv1', 'Clave', 'clave')
    if pv1_value:
        # Search for product by provider-specific pv1
        from im.models import ProductProvider
        pp = ProductProvider.objects.filter(pv1=pv1_value).first()
        if pp:
            return pp.product

    legacy_product_id = get_first_csv_value(row, 'id')
    if legacy_product_id:
        try:
            return Product.objects.filter(id=int(legacy_product_id)).first()
        except (ValueError, TypeError):
            pass

    return None


def get_import_provider():
    return Provider.objects.filter(name='general').first() or Provider.objects.first()


def validate_csv_row(row, row_number):
    errors = []

    product_reference = get_first_csv_value(row, 'product', 'product_id', 'pv1', 'Clave', 'clave', 'id')
    if not product_reference:
        errors.append('missing product reference')

    product = resolve_csv_product(row)
    if product_reference and not product:
        errors.append('product not found')

    quantity_value = get_first_csv_value(row, 'quantity', 'cantidad', 'Cantidad')
    if quantity_value is None:
        quantity = None
        errors.append('quantity is required')
    else:
        try:
            quantity = int(str(quantity_value).strip())
            if quantity <= 0:
                errors.append('quantity must be greater than 0')
        except (TypeError, ValueError):
            quantity = None
            errors.append('quantity must be a whole number')

    cost_value = get_first_csv_value(row, 'cost', 'costo', 'Costo')
    if cost_value is None:
        cost = None
        errors.append('cost is required')
    else:
        try:
            cost = Decimal(str(cost_value).strip().replace(',', ''))
            if cost < 0:
                errors.append('cost must be 0 or greater')
        except (InvalidOperation, TypeError, ValueError):
            cost = None
            errors.append('cost must be numeric')

    return {
        'row_number': row_number,
        'row': row,
        'product': product,
        'quantity': quantity,
        'cost': cost,
        'errors': errors,
    }


def validate_csv_rows(rows):
    return [validate_csv_row(row, index) for index, row in enumerate(rows, start=1)]


def render_csv_validation_response(file_name, validations):
    total_rows = len(validations)
    error_rows = [validation for validation in validations if validation['errors']]
    preview_headers = list(validations[0]['row'].keys())[:4] if validations else []
    preview_rows = validations[:5]

    html = '<div class="alert alert-info">Found {} rows in "{}".</div>'.format(
        total_rows, file_name
    )
    html += (
        '<div class="alert alert-secondary">'
        'A new purchase will be created automatically if the import succeeds. '
        'All rows will be linked to that same purchase.'
        '</div>'
    )

    if error_rows:
        html += (
            '<div class="alert alert-danger">'
            'Import aborted. Fix the CSV before continuing. {} row(s) have errors.'
            '</div>'
        ).format(len(error_rows))
        html += '<ul class="mb-3">'
        for validation in error_rows[:20]:
            html += '<li>Row {}: {}</li>'.format(
                validation['row_number'],
                ', '.join(validation['errors']),
            )
        if len(error_rows) > 20:
            html += '<li>...and {} more row(s).</li>'.format(len(error_rows) - 20)
        html += '</ul>'
    else:
        html += (
            '<div class="alert alert-success">'
            'Validation passed. {} row(s) ready to import.'
            '</div>'
        ).format(total_rows)

    html += '<table class="table table-sm table-bordered mt-3"><thead><tr><th>Row</th>'
    for header in preview_headers:
        html += '<th>{}</th>'.format(header)
    html += '<th>Status</th></tr></thead><tbody>'

    for validation in preview_rows:
        html += '<tr>'
        html += '<td>{}</td>'.format(validation['row_number'])
        for header in preview_headers:
            html += '<td>{}</td>'.format(validation['row'].get(header, ''))
        status = 'OK' if not validation['errors'] else '; '.join(validation['errors'])
        html += '<td>{}</td></tr>'.format(status)

    html += '</tbody></table>'

    if not error_rows:
        html += '''
          <div class="mt-3">
            <button class="btn btn-success" type="button"
                    hx-post="{}" hx-target="#upload-result">
              Import these {} rows
            </button>
          </div>
        '''.format(reverse('scm:uploadcsv_confirm'), total_rows)

    return HttpResponse(html)


def render_csv_validation_response_barcode(file_name, validations):
    """Barcode version of CSV validation response"""
    total_rows = len(validations)
    error_rows = [validation for validation in validations if validation['errors']]
    preview_headers = list(validations[0]['row'].keys())[:4] if validations else []
    preview_rows = validations[:5]

    html = '<div class="alert alert-info">Found {} rows in "{}".</div>'.format(
        total_rows, file_name
    )
    html += (
        '<div class="alert alert-secondary">'
        'A new purchase will be created automatically if the import succeeds. '
        'All rows will be linked to that same purchase.'
        '</div>'
    )

    if error_rows:
        html += (
            '<div class="alert alert-danger">'
            'Import aborted. Fix the CSV before continuing. {} row(s) have errors.'
            '</div>'
        ).format(len(error_rows))
        html += '<ul class="mb-3">'
        for validation in error_rows[:20]:
            html += '<li>Row {}: {}</li>'.format(
                validation['row_number'],
                ', '.join(validation['errors']),
            )
        if len(error_rows) > 20:
            html += '<li>...and {} more row(s).</li>'.format(len(error_rows) - 20)
        html += '</ul>'
    else:
        html += (
            '<div class="alert alert-success">'
            'Validation passed. {} row(s) ready to import.'
            '</div>'
        ).format(total_rows)

    html += '<table class="table table-sm table-bordered mt-3"><thead><tr><th>Row</th>'
    for header in preview_headers:
        html += '<th>{}</th>'.format(header)
    html += '<th>Status</th></tr></thead><tbody>'

    for validation in preview_rows:
        html += '<tr>'
        html += '<td>{}</td>'.format(validation['row_number'])
        for header in preview_headers:
            html += '<td>{}</td>'.format(validation['row'].get(header, ''))
        status = 'OK' if not validation['errors'] else '; '.join(validation['errors'])
        html += '<td>{}</td></tr>'.format(status)

    html += '</tbody></table>'

    if not error_rows:
        html += '''
          <div class="mt-3">
            <button class="btn btn-success" type="button"
                    hx-post="{}" hx-target="#upload-result">
              Import these {} rows
            </button>
          </div>
        '''.format(reverse('scm:uploadcsv_confirm_barcode'), total_rows)

    return HttpResponse(html)


# ------------------------------
# Vista: Subir CSV (solo lectura y preview)
# ------------------------------
def upload_csv_action(request):
    file = request.FILES.get('csv')
    if not file:
        return HttpResponse('<div class="alert alert-danger">No file.</div>')

    decoded = file.read().decode('utf-8-sig', errors='replace').replace('\x00', '')
    sample = decoded[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
    rows = [
        {
            normalize_csv_key(key): value
            for key, value in row.items()
            if normalize_csv_key(key) is not None
        }
        for row in reader
    ]

    if not rows:
        request.session.pop('csv_rows', None)
        return HttpResponse('<div class="alert alert-warning">CSV is empty.</div>')

    validations = validate_csv_rows(rows)
    if any(validation['errors'] for validation in validations):
        request.session.pop('csv_rows', None)
    else:
        request.session['csv_rows'] = rows
        request.session.modified = True

    return render_csv_validation_response(file.name, validations)


# ------------------------------
# Vista: Confirmar e importar CSV
# ------------------------------
def upload_csv_confirm(request):
    rows = request.session.pop('csv_rows', [])
    if not rows:
        return HttpResponse('<div class="alert alert-danger">No data to import.</div>')

    validations = validate_csv_rows(rows)
    error_rows = [validation for validation in validations if validation['errors']]
    if error_rows:
        html = (
            '<div class="alert alert-danger">'
            'Import aborted. No rows were inserted.'
            '</div><ul>'
        )
        for validation in error_rows[:20]:
            html += '<li>Row {}: {}</li>'.format(
                validation['row_number'],
                ', '.join(validation['errors']),
            )
        if len(error_rows) > 20:
            html += '<li>...and {} more row(s).</li>'.format(len(error_rows) - 20)
        html += '</ul>'
        return HttpResponse(html)

    provider = get_import_provider()
    if provider is None:
        return HttpResponse(
            '<div class="alert alert-danger">'
            'Import aborted. No provider is available to create the purchase.'
            '</div>'
        )

    try:
        with transaction.atomic():
            purchase = Purchase.objects.create(provider=provider)
            for validation in validations:
                purchaseItem.objects.create(
                    product=validation['product'],
                    purchase=purchase,
                    quantity=validation['quantity'],
                    cost=str(validation['cost']),
                    date_created=timezone.now(),
                    last_update=timezone.now(),
                )
    except (IntegrityError, ValueError, TypeError) as exc:
        return HttpResponse(
            '<div class="alert alert-danger">'
            'Import aborted. No rows were inserted. Error: {}'
            '</div>'.format(exc)
        )

    html = (
        '<div class="alert alert-success">'
        'Inserted {} new rows into purchase {}. Import completed successfully.'
        '</div>'
    ).format(len(validations), purchase.id)
    html += '<table class="table table-sm table-bordered mt-3"><thead><tr><th>PV1</th><th>Quantity</th></tr></thead><tbody>'
    for validation in validations:
        pv1 = validation['product'].get_pv1()
        html += '<tr><td>{}</td><td>{}</td></tr>'.format(
            pv1 or 'N/A',
            validation['quantity'],
        )
    html += '</tbody></table>'

    return HttpResponse(html)


# ==============================
# Barcode CSV Upload Functions
# ==============================

def resolve_csv_product_barcode(row):
    """Resolve product by barcode for CSV import"""
    product_id_value = get_first_csv_value(row, 'product', 'product_id')
    if product_id_value:
        try:
            product = Product.objects.filter(id=int(product_id_value)).first()
            if product:
                return product
        except (ValueError, TypeError):
            pass

    barcode_value = get_first_csv_value(row, 'barcode', 'Barcode', 'codigo')
    if barcode_value:
        return Product.objects.filter(barcode=barcode_value).first()

    legacy_product_id = get_first_csv_value(row, 'id')
    if legacy_product_id:
        try:
            return Product.objects.filter(id=int(legacy_product_id)).first()
        except (ValueError, TypeError):
            pass

    return None


def validate_csv_row_barcode(row, row_number):
    """Validate CSV row for barcode import"""
    errors = []

    product_reference = get_first_csv_value(row, 'product', 'product_id', 'barcode', 'Barcode', 'codigo', 'id')
    if not product_reference:
        errors.append('missing product reference')

    product = resolve_csv_product_barcode(row)
    if product_reference and not product:
        errors.append('product not found')

    quantity_value = get_first_csv_value(row, 'quantity', 'cantidad', 'Cantidad')
    if quantity_value is None:
        quantity = None
        errors.append('quantity is required')
    else:
        try:
            quantity = int(str(quantity_value).strip())
            if quantity <= 0:
                errors.append('quantity must be greater than 0')
        except (TypeError, ValueError):
            quantity = None
            errors.append('quantity must be a whole number')

    cost_value = get_first_csv_value(row, 'cost', 'costo', 'Costo')
    if cost_value is None:
        cost = None
        errors.append('cost is required')
    else:
        try:
            cost = Decimal(str(cost_value).strip().replace(',', ''))
            if cost < 0:
                errors.append('cost must be 0 or greater')
        except (InvalidOperation, TypeError, ValueError):
            cost = None
            errors.append('cost must be numeric')

    return {
        'row_number': row_number,
        'row': row,
        'product': product,
        'quantity': quantity,
        'cost': cost,
        'errors': errors,
    }


def validate_csv_rows_barcode(rows):
    """Validate all CSV rows for barcode import"""
    return [validate_csv_row_barcode(row, index) for index, row in enumerate(rows, start=1)]


def upload_csv_barcode(request):
    """Render barcode CSV upload form"""
    return render(request, "purchase/upload_purchase_items_barcode.html")


def upload_csv_action_barcode(request):
    """Process barcode CSV file upload"""
    file = request.FILES.get('csv')
    if not file:
        return HttpResponse('<div class="alert alert-danger">No file.</div>')

    decoded = file.read().decode('utf-8-sig', errors='replace').replace('\x00', '')
    sample = decoded[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
    rows = [
        {
            normalize_csv_key(key): value
            for key, value in row.items()
            if normalize_csv_key(key) is not None
        }
        for row in reader
    ]

    if not rows:
        request.session.pop('csv_rows_barcode', None)
        return HttpResponse('<div class="alert alert-warning">CSV is empty.</div>')

    validations = validate_csv_rows_barcode(rows)
    if any(validation['errors'] for validation in validations):
        request.session.pop('csv_rows_barcode', None)
    else:
        request.session['csv_rows_barcode'] = rows
        request.session.modified = True

    return render_csv_validation_response_barcode(file.name, validations)


def upload_csv_confirm_barcode(request):
    """Confirm and import barcode CSV data"""
    rows = request.session.pop('csv_rows_barcode', [])
    if not rows:
        return HttpResponse('<div class="alert alert-danger">No data to import.</div>')

    validations = validate_csv_rows_barcode(rows)
    error_rows = [validation for validation in validations if validation['errors']]
    if error_rows:
        html = (
            '<div class="alert alert-danger">'
            'Import aborted. No rows were inserted.'
            '</div><ul>'
        )
        for validation in error_rows[:20]:
            html += '<li>Row {}: {}</li>'.format(
                validation['row_number'],
                ', '.join(validation['errors']),
            )
        if len(error_rows) > 20:
            html += '<li>...and {} more row(s).</li>'.format(len(error_rows) - 20)
        html += '</ul>'
        return HttpResponse(html)

    provider = get_import_provider()
    if provider is None:
        return HttpResponse(
            '<div class="alert alert-danger">'
            'Import aborted. No provider is available to create the purchase.'
            '</div>'
        )

    try:
        with transaction.atomic():
            purchase = Purchase.objects.create(provider=provider)
            for validation in validations:
                purchaseItem.objects.create(
                    product=validation['product'],
                    purchase=purchase,
                    quantity=validation['quantity'],
                    cost=str(validation['cost']),
                    date_created=timezone.now(),
                    last_update=timezone.now(),
                )
    except (IntegrityError, ValueError, TypeError) as exc:
        return HttpResponse(
            '<div class="alert alert-danger">'
            'Import aborted. No rows were inserted. Error: {}'
            '</div>'.format(exc)
        )

    html = (
        '<div class="alert alert-success">'
        'Inserted {} new rows into purchase {}. Import completed successfully.'
        '</div>'
    ).format(len(validations), purchase.id)
    html += '<table class="table table-sm table-bordered mt-3"><thead><tr><th>Barcode</th><th>Quantity</th></tr></thead><tbody>'
    for validation in validations:
        html += '<tr><td>{}</td><td>{}</td></tr>'.format(
            validation['product'].barcode,
            validation['quantity'],
        )
    html += '</tbody></table>'

    return HttpResponse(html)


@csrf_exempt
def mark_ready_to_sale(request):
    """Mark a purchase and its inventory items as ready to sale"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    purchase_id = request.POST.get('purchase_id')
    
    if not purchase_id:
        return JsonResponse({'success': False, 'message': 'Purchase ID required'})
    
    try:
        from django.db.models import Q
        from im.models import InventoryUnit
        
        purchase = Purchase.objects.get(id=purchase_id)
        
        # Get all purchase items for this purchase
        purchase_items = purchase.purchaseitem_set.all()
        
        if not purchase_items.exists():
            return JsonResponse({'success': False, 'message': 'No items found in this purchase'})
        
        # IMPORTANT: Only update inventory units that are directly linked to this purchase's items
        # Do NOT use product_id search as it would update units from other purchases
        
        updated_count = 0
        purchase_item_ids = purchase_items.values_list('id', flat=True)
        
        # Update units directly linked to this purchase's items
        units = InventoryUnit.objects.filter(
            purchase_item_id__in=purchase_item_ids,
            status__in=['received', 'ordered', 'send']
        )
        
        updated_count = units.update(status='ready_to_sale')
        
        if updated_count > 0:
            return JsonResponse({
                'success': True,
                'message': f'✓ {updated_count} unidades marcadas como Listo para Venta'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'No hay unidades de inventario en estado recibido para esta compra. Items en compra: {purchase_items.count()}'
            })
    
    except Purchase.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Purchase not found'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
