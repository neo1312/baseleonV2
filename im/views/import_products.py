from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from im.forms import ProductCSVUploadForm
from im.management.commands.import_products_csv import Command
from crm.decorators import role_required
import csv
from io import StringIO

TEMPLATE = 'admin/import_products.html'


@login_required
@role_required('Admin', 'Manager', 'Buyer')
def import_products_csv_view(request):
    """Frontend view for bulk importing products from CSV with preview"""
    
    if request.method == 'POST' and 'confirm_import' in request.POST:
        # STEP 2: Confirm and import
        preview_data = request.session.get('csv_preview_data', {})
        skip_errors = request.session.get('csv_skip_errors', False)
        
        try:
            cmd = Command()
            created = 0
            updated = 0
            errors = 0
            
            for row_num, row in enumerate(preview_data.get('rows', []), start=2):
                try:
                    product_data = cmd._parse_row(row)
                    from im.models import Product
                    product, is_new = Product.objects.update_or_create(
                        barcode=product_data['barcode'],
                        defaults=product_data
                    )
                    if is_new:
                        created += 1
                    else:
                        updated += 1
                except Exception as e:
                    errors += 1
                    if not skip_errors:
                        messages.error(request, f"Row {row_num}: {str(e)}")
                        return redirect('im:import_products_csv')
            
            messages.success(
                request,
                f"Import complete! Created: {created} | Updated: {updated} | Errors: {errors}"
            )
            request.session.pop('csv_preview_data', None)
            request.session.pop('csv_skip_errors', None)
            return redirect('im:import_products_csv')
            
        except Exception as e:
            messages.error(request, f"Error during import: {str(e)}")
            return redirect('im:import_products_csv')
    
    elif request.method == 'POST' and 'csv_file' in request.FILES:
        # STEP 1: Preview
        form = ProductCSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            skip_errors = form.cleaned_data['skip_errors']
            
            try:
                decoded_file = csv_file.read().decode('utf-8')
                csv_reader = csv.DictReader(StringIO(decoded_file))
                
                if not csv_reader.fieldnames:
                    messages.error(request, "CSV file is empty or invalid")
                    return redirect('im:import_products_csv')
                
                rows = list(csv_reader)
                if not rows:
                    messages.error(request, "CSV file has no data rows")
                    return redirect('im:import_products_csv')
                
                request.session['csv_preview_data'] = {'rows': rows}
                request.session['csv_skip_errors'] = skip_errors
                
                context = {
                    'form': form,
                    'preview': True,
                    'total_rows': len(rows),
                    'rows': rows[:5],
                    'skip_errors': skip_errors,
                }
                return render(request, TEMPLATE, context)
                
            except Exception as e:
                messages.error(request, f"Error reading file: {str(e)}")
    else:
        form = ProductCSVUploadForm()
    
    return render(request, TEMPLATE, {'form': form, 'preview': False})
