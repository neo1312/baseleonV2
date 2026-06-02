from django.db import migrations


def backfill_purchase_with_iva(apps, schema_editor):
    InventoryUnit = apps.get_model('im', 'InventoryUnit')
    PurchaseOrder = apps.get_model('scm', 'PurchaseOrder')

    po_ids_with_iva = list(
        PurchaseOrder.objects.filter(has_iva=True).values_list('pk', flat=True)
    )
    InventoryUnit.objects.filter(
        purchase_order_id__in=po_ids_with_iva,
        purchase_with_iva=False,
    ).update(purchase_with_iva=True)

    po_ids_without_iva = list(
        PurchaseOrder.objects.filter(has_iva=False).values_list('pk', flat=True)
    )
    InventoryUnit.objects.filter(
        purchase_order_id__in=po_ids_without_iva,
        purchase_with_iva=True,
    ).update(purchase_with_iva=False)


class Migration(migrations.Migration):

    dependencies = [
        ('im', '0072_inventoryunit_purchase_with_iva'),
        ('scm', '0015_purchaseorder_has_iva'),
    ]

    operations = [
        migrations.RunPython(backfill_purchase_with_iva, migrations.RunPython.noop),
    ]
