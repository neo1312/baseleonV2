from django.db import migrations


def backfill_purchase_with_iva(apps, schema_editor):
    InventoryUnit = apps.get_model('im', 'InventoryUnit')

    units = InventoryUnit.objects.filter(
        purchase_order__isnull=False
    ).select_related('purchase_order')

    updated = 0
    for unit in units:
        if unit.purchase_order.has_iva and not unit.purchase_with_iva:
            unit.purchase_with_iva = True
            unit.save(update_fields=['purchase_with_iva'])
            updated += 1
        elif not unit.purchase_order.has_iva and unit.purchase_with_iva:
            unit.purchase_with_iva = False
            unit.save(update_fields=['purchase_with_iva'])
            updated += 1


class Migration(migrations.Migration):

    dependencies = [
        ('im', '0072_inventoryunit_purchase_with_iva'),
    ]

    operations = [
        migrations.RunPython(backfill_purchase_with_iva, migrations.RunPython.noop),
    ]
