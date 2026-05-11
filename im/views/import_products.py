from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from im.forms import ProductCSVUploadForm
from im.management.commands.import_products_csv import Command
import csv
from io import StringIO
import tempfile
import os
import json

def staff_required(view_func):
    """Decorator to require staff permission"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('admin:login')
        return view_func(request, *args, **kwargs)
    return wrapper

@staff_required
def import_products_csv_view(request):
    """Admin view for bulk importing products from CSV with preview"""
    
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
                f"✅ Import complete!\nCreated: {created} | Updated: {updated} | Errors: {errors}"
            )
            # Clean up session data
            request.session.pop('csv_preview_data', None)
            request.session.pop('csv_skip_errors', None)
            return redirect('admin:im_product_changelist')
            
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
                
                # Store preview data in session
                request.session['csv_preview_data'] = {'rows': rows}
                request.session['csv_skip_errors'] = skip_errors
                
                # Show preview
                context = {
                    'form': form,
                    'preview': True,
                    'total_rows': len(rows),
                    'rows': rows[:5],  # Show first 5 rows
                    'skip_errors': skip_errors,
                }
                return render(request, 'admin/import_products.html', context)
                
            except Exception as e:
                messages.error(request, f"Error reading file: {str(e)}")
    else:
        form = ProductCSVUploadForm()
    
    return render(request, 'admin/import_products.html', {'form': form, 'preview': False})
