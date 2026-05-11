# Data migration to populate clave field with product ID for existing products

from django.db import migrations


def populate_clave(apps, schema_editor):
    """Populate clave field with product ID for all existing products"""
    Product = apps.get_model('im', 'Product')
    for product in Product.objects.all():
        if not product.clave:
            product.clave = str(product.id)
            product.save()


def reverse_populate_clave(apps, schema_editor):
    """Clear clave field when rolling back"""
    Product = apps.get_model('im', 'Product')
    Product.objects.all().update(clave=None)


class Migration(migrations.Migration):

    dependencies = [
        ('im', '0051_product_clave'),
    ]

    operations = [
        migrations.RunPython(populate_clave, reverse_populate_clave),
    ]
