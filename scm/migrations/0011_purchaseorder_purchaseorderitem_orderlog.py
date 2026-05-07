import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('im', '0039_demandforecast_forecastconfiguration'),
        ('scm', '0010_repair_purchaseitem_sequence'),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('po_number', models.CharField(max_length=50, unique=True, verbose_name='PO Number')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('approved', 'Approved'), ('sent', 'Sent to Supplier'), ('received', 'Received'), ('completed', 'Completed')], default='draft', max_length=20, verbose_name='Status')),
                ('created_by', models.CharField(blank=True, max_length=150, null=True, verbose_name='Created By')),
                ('approved_by', models.CharField(blank=True, max_length=150, null=True, verbose_name='Approved By')),
                ('received_by', models.CharField(blank=True, max_length=150, null=True, verbose_name='Received By')),
                ('completed_by', models.CharField(blank=True, max_length=150, null=True, verbose_name='Completed By')),
                ('creation_method', models.CharField(choices=[('auto_forecast', 'Auto from Forecast'), ('manual_stock', 'Manual from Min/Max')], default='manual_stock', max_length=20, verbose_name='Creation Method')),
                ('tracking_reference', models.CharField(blank=True, max_length=100, null=True, verbose_name='Supplier Tracking Reference')),
                ('created_date', models.DateTimeField(auto_now_add=True, verbose_name='Created Date')),
                ('approved_date', models.DateTimeField(blank=True, null=True, verbose_name='Approved Date')),
                ('sent_date', models.DateTimeField(blank=True, null=True, verbose_name='Sent Date')),
                ('received_date', models.DateTimeField(blank=True, null=True, verbose_name='Received Date')),
                ('completed_date', models.DateTimeField(blank=True, null=True, verbose_name='Completed Date')),
                ('total_items', models.IntegerField(default=0, verbose_name='Total Items')),
                ('total_ordered_cost', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Total Ordered Cost')),
                ('total_received_cost', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Total Received Cost')),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='scm.provider', verbose_name='Supplier')),
            ],
            options={
                'verbose_name': 'Purchase Order',
                'verbose_name_plural': 'Purchase Orders',
                'ordering': ['-created_date'],
            },
        ),
        migrations.CreateModel(
            name='PurchaseOrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ordered_quantity', models.IntegerField(verbose_name='Ordered Quantity')),
                ('received_quantity', models.IntegerField(default=0, verbose_name='Received Quantity')),
                ('ordered_cost_per_unit', models.DecimalField(decimal_places=6, max_digits=10, verbose_name='Ordered Cost per Unit')),
                ('received_cost_per_unit', models.DecimalField(blank=True, decimal_places=6, max_digits=10, null=True, verbose_name='Received Cost per Unit')),
                ('ordered_total', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Ordered Total')),
                ('received_total', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Received Total')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='im.product', verbose_name='Product')),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='scm.purchaseorder', verbose_name='Purchase Order')),
            ],
            options={
                'verbose_name': 'Purchase Order Item',
                'verbose_name_plural': 'Purchase Order Items',
                'unique_together': {('purchase_order', 'product')},
            },
        ),
        migrations.CreateModel(
            name='OrderLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('created', 'Order Created'), ('quantity_changed', 'Quantity Changed'), ('cost_changed', 'Cost Changed'), ('approved', 'Order Approved'), ('sent', 'Order Sent'), ('received', 'Order Received'), ('received_qty_changed', 'Received Quantity Changed'), ('received_cost_changed', 'Received Cost Changed'), ('completed', 'Order Completed'), ('status_changed', 'Status Changed')], max_length=30, verbose_name='Action')),
                ('performed_by', models.CharField(max_length=150, verbose_name='Performed By')),
                ('field_name', models.CharField(blank=True, max_length=50, null=True, verbose_name='Field Changed')),
                ('old_value', models.TextField(blank=True, null=True, verbose_name='Old Value')),
                ('new_value', models.TextField(blank=True, null=True, verbose_name='New Value')),
                ('notes', models.TextField(blank=True, null=True, verbose_name='Notes')),
                ('timestamp', models.DateTimeField(auto_now_add=True, verbose_name='Timestamp')),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='scm.purchaseorder', verbose_name='Purchase Order')),
                ('po_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='scm.purchaseorderitem', verbose_name='PO Item')),
            ],
            options={
                'verbose_name': 'Order Log',
                'verbose_name_plural': 'Order Logs',
                'ordering': ['-timestamp'],
            },
        ),
    ]
