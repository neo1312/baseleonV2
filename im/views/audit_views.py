"""
Inventory Audit Views
Handles audit cycles, product counting, and discrepancy adjustments
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal
import random

from im.models import InventoryAudit, AuditItem, AdjustmentTransaction, Product, InventoryUnit
from django.db.models import Count, Q, Sum, Avg, F
from django.db.models import DecimalField
from crm.decorators import role_required


@require_http_methods(["GET", "POST"])
@role_required('Admin', 'Manager', 'Auditor')
def audit_start(request):
    """Start a new inventory audit"""
    if request.method == 'POST':
        audit_type = request.POST.get('audit_type')
        auditor = request.POST.get('auditor') or str(request.user)
        notes = request.POST.get('notes', '')
        
        if not audit_type:
            messages.error(request, 'Audit type is required')
            return redirect('im:audit_start')
        
        # Create audit
        audit = InventoryAudit.objects.create(
            audit_type=audit_type,
            auditor=auditor,
            notes=notes,
            status='draft'
        )
        
        # Redirect to product selection
        return redirect('im:audit_select_products', audit_id=audit.id)
    
    context = {
        'title': 'Start Inventory Audit',
        'audit_types': InventoryAudit.AUDIT_TYPE_CHOICES,
    }
    return render(request, 'audit/start.html', context)


@require_http_methods(["GET", "POST"])
@role_required('Admin', 'Manager', 'Auditor')
def audit_select_products(request, audit_id):
    """Select products for audit based on audit type"""
    audit = get_object_or_404(InventoryAudit, id=audit_id, status='draft')
    
    if request.method == 'POST':
        product_ids = request.POST.getlist('product_ids')
        
        if not product_ids:
            messages.error(request, 'Select at least one product')
            return redirect('im:audit_select_products', audit_id=audit_id)
        
        # Create audit items for selected products
        products = Product.objects.filter(id__in=product_ids)
        
        for product in products:
            system_count = InventoryUnit.objects.filter(
                product=product,
                status='ready_to_sale'
            ).count()
            
            AuditItem.objects.create(
                audit=audit,
                product=product,
                system_count=system_count,
                physical_count=0,  # Will be filled in during counting
            )
        
        audit.status = 'in_progress'
        audit.started_at = timezone.now()
        audit.save()
        
        messages.success(request, f'Audit started with {len(products)} products')
        return redirect('im:audit_enter_counts', audit_id=audit_id)
    
    # Determine products to display based on audit type
    if audit.audit_type == 'random':
        sample_size = 20
        all_products = list(Product.objects.filter(active=True))
        selected_products = random.sample(all_products, min(sample_size, len(all_products)))
    
    elif audit.audit_type == 'random_custom':
        sample_size = int(request.GET.get('sample_size', 20))
        all_products = list(Product.objects.filter(active=True))
        selected_products = random.sample(all_products, min(sample_size, len(all_products)))
    
    elif audit.audit_type == 'full':
        selected_products = Product.objects.filter(active=True).all()
    
    elif audit.audit_type == 'category':
        category_id = request.GET.get('category_id')
        if category_id:
            selected_products = Product.objects.filter(active=True, category_id=category_id)
        else:
            selected_products = Product.objects.filter(active=True).all()
    
    elif audit.audit_type == 'manual':
        selected_products = Product.objects.filter(active=True).all()
    
    else:
        selected_products = []
    
    context = {
        'title': 'Select Products for Audit',
        'audit': audit,
        'products': selected_products,
        'audit_type': audit.get_audit_type_display(),
    }
    return render(request, 'audit/select_products.html', context)


@require_http_methods(["GET", "POST"])
def audit_enter_counts(request, audit_id):
    """Enter physical counts for audit items"""
    audit = get_object_or_404(InventoryAudit, id=audit_id, status='in_progress')
    audit_items = audit.items.all()
    
    if request.method == 'POST':
        # Process count submissions
        for item in audit_items:
            physical_count = request.POST.get(f'physical_count_{item.id}')
            if physical_count is not None:
                try:
                    item.physical_count = int(physical_count)
                    item.save()
                except (ValueError, TypeError):
                    messages.error(request, f'Invalid count for {item.product.name}')
                    return redirect('im:audit_enter_counts', audit_id=audit_id)
        
        messages.success(request, 'Counts entered. Proceed to review discrepancies.')
        return redirect('im:audit_review', audit_id=audit_id)
    
    context = {
        'title': 'Enter Physical Counts',
        'audit': audit,
        'items': audit_items,
    }
    return render(request, 'audit/enter_counts.html', context)


@require_http_methods(["GET", "POST"])
def audit_review(request, audit_id):
    """Review and approve discrepancies"""
    audit = get_object_or_404(InventoryAudit, id=audit_id, status='in_progress')
    audit_items = audit.items.filter(discrepancy__gt=0) | audit.items.filter(discrepancy__lt=0)
    
    if request.method == 'POST':
        # Process adjustment approvals
        for item in audit_items:
            adjustment_reason = request.POST.get(f'adjustment_reason_{item.id}')
            approved = request.POST.get(f'approved_{item.id}')
            notes = request.POST.get(f'notes_{item.id}', '')
            
            if approved and adjustment_reason:
                item.adjustment_reason = adjustment_reason
                item.adjustment_status = 'approved'
                item.notes = notes
                item.verified_by = str(request.user)
                item.save()
        
        audit.status = 'under_review'
        audit.reviewed_by = str(request.user)
        audit.save()
        
        messages.success(request, 'Adjustments approved. Ready to apply.')
        return redirect('im:audit_apply_adjustments', audit_id=audit_id)
    
    context = {
        'title': 'Review Discrepancies',
        'audit': audit,
        'items': audit_items,
        'adjustment_reasons': AuditItem.ADJUSTMENT_REASON_CHOICES,
    }
    return render(request, 'audit/review.html', context)


@require_http_methods(["GET", "POST"])
def audit_apply_adjustments(request, audit_id):
    """Apply approved adjustments and create transactions"""
    audit = get_object_or_404(InventoryAudit, id=audit_id, status='under_review')
    approved_items = audit.items.filter(adjustment_status='approved')
    
    if request.method == 'POST':
        apply_adjustments = request.POST.get('apply_adjustments') == 'yes'
        
        if apply_adjustments:
            for item in approved_items:
                if item.discrepancy != 0 and item.product:
                    # Create adjustment transaction
                    adjustment = AdjustmentTransaction.objects.create(
                        audit_item=item,
                        product=item.product,
                        adjustment_reason=item.adjustment_reason,
                        quantity_adjusted=item.discrepancy,
                        unit_cost=item.product.costo or Decimal('0'),
                        recorded_by=str(request.user),
                        status='applied',
                        applied_by=str(request.user),
                        applied_at=timezone.now(),
                    )
                    
                    # Update inventory based on discrepancy
                    if item.discrepancy > 0:
                        # More physical than system - need to add inventory
                        for i in range(int(item.discrepancy)):
                            InventoryUnit.objects.create(
                                tracking_id=f"AUDIT-{audit.id}-{item.id}-{i}",
                                product=item.product,
                                status='ready_to_sale',
                                purchase_cost=item.product.costo or Decimal('0'),
                                received_cost=item.product.costo or Decimal('0'),
                                received_date=timezone.now(),
                            )
                    elif item.discrepancy < 0:
                        # Less physical than system - retire inventory
                        units_to_retire = InventoryUnit.objects.filter(
                            product=item.product,
                            status='ready_to_sale'
                        ).order_by('received_date')[:abs(int(item.discrepancy))]
                        
                        # Map adjustment reason to retirement status
                        reason_to_status = {
                            'stolen': 'retired_stolen',
                            'damaged': 'retired_damaged',
                            'warranty': 'retired_warranty',
                            'miscounted': 'retired_miscounted',
                            'expired': 'retired_expired',
                            'shrinkage': 'retired_shrinkage',
                            'correction': 'retired_correction',
                            'other': 'retired_other',
                        }
                        retirement_status = reason_to_status.get(item.adjustment_reason, 'retired_other')
                        
                        for unit in units_to_retire:
                            unit.status = retirement_status
                            unit.retired_date = timezone.now()
                            unit.save()
                    
                    item.adjustment_status = 'applied'
                    item.approved_by = str(request.user)
                    item.save()
            
            audit.status = 'completed'
            audit.completed_at = timezone.now()
            audit.save()
            audit.update_stats()
            
            messages.success(request, f'Applied {approved_items.count()} adjustments')
            return redirect('im:audit_summary', audit_id=audit_id)
        else:
            audit.status = 'completed'
            audit.completed_at = timezone.now()
            audit.save()
            audit.update_stats()
            
            messages.warning(request, 'Audit completed without applying adjustments')
            return redirect('im:audit_summary', audit_id=audit_id)
    
    context = {
        'title': 'Apply Adjustments',
        'audit': audit,
        'items': approved_items,
        'total_adjustments': approved_items.count(),
    }
    
    # Calculate impact for each item and total impact
    total_impact = Decimal('0')
    for item in approved_items:
        item.impact = (item.discrepancy or 0) * (item.product.costo or Decimal('0'))
        item.impact_abs = abs(item.impact)
        total_impact += item.impact_abs
    
    context['total_impact'] = total_impact
    return render(request, 'audit/apply_adjustments.html', context)


@require_http_methods(["GET"])
def audit_summary(request, audit_id):
    """View audit summary and results"""
    audit = get_object_or_404(InventoryAudit, id=audit_id)
    audit_items = audit.items.all()
    adjustments = AdjustmentTransaction.objects.filter(audit_item__audit=audit)
    
    # Calculate statistics
    total_discrepancies = audit_items.exclude(discrepancy=0).count()
    positive_discrepancies = audit_items.filter(discrepancy__gt=0).count()
    negative_discrepancies = audit_items.filter(discrepancy__lt=0).count()
    
    # By reason
    by_reason = {}
    for item in audit_items.exclude(adjustment_reason__isnull=True):
        reason = item.get_adjustment_reason_display()
        by_reason[reason] = by_reason.get(reason, 0) + 1
    
    context = {
        'title': f'Audit Summary #{audit.id}',
        'audit': audit,
        'items': audit_items,
        'adjustments': adjustments,
        'total_discrepancies': total_discrepancies,
        'positive_discrepancies': positive_discrepancies,
        'negative_discrepancies': negative_discrepancies,
        'by_reason': by_reason,
    }
    return render(request, 'audit/summary.html', context)


@require_http_methods(["GET"])
def audit_list(request):
    """List all audits"""
    from datetime import date
    from django.db.models import Q
    
    audits = InventoryAudit.objects.all().order_by('-audit_date')
    
    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        audits = audits.filter(status=status_filter)
    
    # Filter by date range
    today = date.today()
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    
    # Default to today if not provided
    if not from_date:
        from_date = str(today)
    if not to_date:
        to_date = str(today)
    
    try:
        from_date_obj = date.fromisoformat(from_date)
        to_date_obj = date.fromisoformat(to_date)
        audits = audits.filter(audit_date__gte=from_date_obj, audit_date__lte=to_date_obj)
    except ValueError:
        pass  # Invalid date format, ignore filter
    
    context = {
        'title': 'Inventory Audits',
        'audits': audits,
        'status_choices': InventoryAudit.STATUS_CHOICES,
        'current_status': status_filter,
        'from_date': from_date,
        'to_date': to_date,
    }
    return render(request, 'audit/list.html', context)


@require_http_methods(["POST"])
def audit_delete(request, audit_id):
    """Delete an incomplete audit"""
    audit = get_object_or_404(InventoryAudit, id=audit_id)
    
    # Only allow deletion of non-completed audits
    if audit.status == 'completed':
        messages.error(request, 'Cannot delete a completed audit')
        return redirect('im:audit_list')
    
    audit_name = f"Audit #{audit.id} ({audit.get_audit_type_display()})"
    audit.delete()
    messages.success(request, f'Deleted: {audit_name}')
    return redirect('im:audit_list')


@require_http_methods(["GET"])
def audit_reports(request):
    """Audit reports and analytics dashboard with sales and devolution integration"""
    from django.db.models import Sum, Count, Avg, F, Case, When, Value, DecimalField as DecField
    from datetime import date, timedelta
    import json
    from crm.models import saleItem, devolutionItem
    
    # Get date range
    today = date.today()
    days_back = int(request.GET.get('days', 30))
    start_date = today - timedelta(days=days_back)
    
    # Filter completed audits
    audits = InventoryAudit.objects.filter(
        status='completed',
        audit_date__gte=start_date,
        audit_date__lte=today
    ).order_by('-audit_date')
    
    # Overall Statistics
    total_audits = audits.count()
    total_items_audited = audits.aggregate(Sum('total_items_audited'))['total_items_audited__sum'] or 0
    total_discrepancies = audits.aggregate(Sum('total_discrepancies'))['total_discrepancies__sum'] or 0
    
    # AUDIT IMPACT: Calculate profit based on selling price (price - cost) × quantity
    audit_profit = Decimal('0')
    for item in AuditItem.objects.filter(audit__in=audits).exclude(discrepancy=0):
        if item.product:
            # Calculate selling price from margin
            if item.product.pricing_mode == 'price' and item.product.precio_manual:
                price = item.product.precio_manual
            else:
                margin = Decimal(str(item.product.margen)) if item.product.margen else Decimal('1')
                price = item.product.costo * (1 + margin)
            
            profit_per_unit = price - item.product.costo
            audit_profit += item.discrepancy * profit_per_unit
    
    # SALES PROFIT: Calculate profit from actual sales
    # Use __date to extract date component from DateTimeField for proper daily filtering
    sales = saleItem.objects.filter(sale__date_created__date__gte=start_date, sale__date_created__date__lte=today)
    sales_profit = Decimal('0')
    for sale_item in sales:
        if sale_item.product:
            # Calculate selling price from margin
            if sale_item.product.pricing_mode == 'price' and sale_item.product.precio_manual:
                price = sale_item.product.precio_manual
            else:
                margin = Decimal(str(sale_item.product.margen)) if sale_item.product.margen else Decimal('1')
                price = sale_item.product.costo * (1 + margin)
            
            profit_per_unit = price - sale_item.product.costo
            qty = Decimal(str(sale_item.quantity)) if sale_item.quantity else Decimal('0')
            sales_profit += qty * profit_per_unit
    
    # DEVOLUTION IMPACT: Calculate loss from devolutions
    # Use __date to extract date component from DateTimeField for proper daily filtering
    devolutions = devolutionItem.objects.filter(devolution__date_created__date__gte=start_date, devolution__date_created__date__lte=today)
    devolution_loss = Decimal('0')
    for dev_item in devolutions:
        if dev_item.producto:
            # Calculate selling price from margin
            if dev_item.producto.pricing_mode == 'price' and dev_item.producto.precio_manual:
                price = dev_item.producto.precio_manual
            else:
                margin = Decimal(str(dev_item.producto.margen)) if dev_item.producto.margen else Decimal('1')
                price = dev_item.producto.costo * (1 + margin)
            
            profit_per_unit = price - dev_item.producto.costo
            qty = Decimal(str(dev_item.cantidad)) if dev_item.cantidad else Decimal('0')
            # Devolutions are negative (loss of profit)
            devolution_loss -= qty * profit_per_unit
    
    total_impact = audit_profit + sales_profit + devolution_loss
    
    # Discrepancies by Reason - with profit calculation
    reason_stats_raw = AuditItem.objects.filter(
        audit__in=audits
    ).exclude(
        discrepancy=0
    ).values('adjustment_reason').annotate(
        count=Count('id'),
        total_qty=Sum('discrepancy')
    ).order_by('-count')
    
    reason_stats = []
    for reason in reason_stats_raw:
        # Recalculate profit for this reason
        items = AuditItem.objects.filter(
            audit__in=audits,
            adjustment_reason=reason['adjustment_reason']
        ).exclude(discrepancy=0)
        
        profit = Decimal('0')
        for item in items:
            if item.product:
                if item.product.pricing_mode == 'price' and item.product.precio_manual:
                    price = item.product.precio_manual
                else:
                    margin = Decimal(str(item.product.margen)) if item.product.margen else Decimal('1')
                    price = item.product.costo * (1 + margin)
                profit_per_unit = price - item.product.costo
                profit += item.discrepancy * profit_per_unit
        
        reason['total_value'] = profit
        reason['percentage'] = 0
        reason_stats.append(reason)
    
    # Calculate percentages
    if total_impact != 0:
        for reason in reason_stats:
            reason['percentage'] = (float(reason['total_value']) / float(total_impact) * 100)
    
    # Top 10 Products with Issues
    problem_products = AuditItem.objects.filter(
        audit__in=audits
    ).exclude(
        discrepancy=0
    ).values('product__name', 'product__barcode', 'product__costo', 'product__margen', 'product__pricing_mode', 'product__precio_manual').annotate(
        discrepancy_count=Count('id'),
        total_discrepancy=Sum('discrepancy'),
        avg_discrepancy=Avg('discrepancy')
    ).order_by('-discrepancy_count')[:10]
    
    # Calculate profit for each product
    for product in problem_products:
        if product['product__costo']:
            if product['product__pricing_mode'] == 'price' and product['product__precio_manual']:
                price = product['product__precio_manual']
            else:
                margin = Decimal(str(product['product__margen'])) if product['product__margen'] else Decimal('1')
                price = product['product__costo'] * (1 + margin)
            profit_per_unit = price - Decimal(str(product['product__costo']))
            product['profit_impact'] = product['total_discrepancy'] * profit_per_unit
        else:
            product['profit_impact'] = Decimal('0')
    
    # Audit Trends (by date)
    daily_audits = audits.extra(
        select={'audit_date_only': 'DATE(audit_date)'}
    ).values('audit_date_only').annotate(
        count=Count('id'),
        total_items=Sum('total_items_audited'),
        total_disc=Sum('total_discrepancies'),
        total_val=Sum('total_adjustment_value')
    ).order_by('audit_date_only')
    
    # Prepare chart data
    chart_dates = [d['audit_date_only'] if isinstance(d['audit_date_only'], str) else d['audit_date_only'].isoformat() for d in daily_audits]
    chart_items = [d['total_items'] or 0 for d in daily_audits]
    chart_disc = [d['total_disc'] or 0 for d in daily_audits]
    chart_val = [float(d['total_val'] or 0) for d in daily_audits]
    
    # Reason chart data
    reason_labels = []
    reason_counts = []
    reason_values = []
    reason_colors = {
        'stolen': '#dc3545',
        'damaged': '#ff9800',
        'warranty': '#2196f3',
        'miscounted': '#9c27b0',
        'expired': '#cddc39',
        'shrinkage': '#f44336',
        'correction': '#4caf50',
        'other': '#9e9e9e',
    }
    
    for reason in reason_stats:
        reason_key = reason['adjustment_reason'] or 'unknown'
        reason_labels.append(dict(AuditItem.ADJUSTMENT_REASON_CHOICES).get(reason_key, reason_key))
        reason_counts.append(reason['count'])
        reason_values.append(float(reason['total_value'] or 0))
    
    # Calculate percentages for each reason
    for reason in reason_stats:
        total_val = float(reason['total_value'] or 0)
        if total_impact > 0:
            reason['percentage'] = (total_val / float(total_impact) * 100)
        else:
            reason['percentage'] = 0
    
    context = {
        'title': 'Audit Reports & Analytics',
        'total_audits': total_audits,
        'total_items_audited': total_items_audited,
        'total_discrepancies': total_discrepancies,
        'total_impact': float(total_impact),
        'avg_discrepancy_rate': (total_discrepancies / total_items_audited * 100) if total_items_audited > 0 else 0,
        'days_back': days_back,
        'days_options': [7, 30, 90],
        
        # Profit breakdown
        'sales_profit': float(sales_profit),
        'audit_profit': float(audit_profit),
        'devolution_loss': float(devolution_loss),
        
        # Charts data
        'chart_dates': json.dumps(chart_dates),
        'chart_items': json.dumps(chart_items),
        'chart_disc': json.dumps(chart_disc),
        'chart_val': json.dumps(chart_val),
        
        'reason_labels': json.dumps(reason_labels),
        'reason_counts': json.dumps(reason_counts),
        'reason_values': json.dumps(reason_values),
        'reason_colors': json.dumps(list(reason_colors.values())[:len(reason_labels)]) if reason_labels else '[]',
        
        'problem_products': problem_products,
        'reason_stats': reason_stats,
        'total_value': total_impact,
    }
    
    return render(request, 'audit/reports.html', context)
