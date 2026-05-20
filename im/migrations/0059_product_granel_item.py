# Generated manually - adds Granel_Item boolean field to Product

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('im', '0058_productgroup_product_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='Granel_Item',
            field=models.BooleanField(default=False, verbose_name='Granel Item'),
        ),
    ]
