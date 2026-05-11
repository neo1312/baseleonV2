# Generated migration for adding clave field to Product

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('im', '0050_remove_product_unique_product_full_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='clave',
            field=models.CharField(
                blank=True,
                help_text="Unique identifier for the product. Defaults to the product ID.",
                max_length=100,
                null=True,
                unique=True,
                verbose_name='Clave'
            ),
        ),
    ]
