import datetime
from decimal import Decimal
from django.db import migrations, models
from django.utils import timezone


def migrate_cutoff_times(apps, schema_editor):
    CajaConfig = apps.get_model('crm', 'CajaConfig')
    config = CajaConfig.objects.filter(pk=1).first()
    if config:
        old_time = getattr(config, 'cutoff_time', timezone.datetime.strptime('17:30', '%H:%M').time())
        old_sat = getattr(config, 'cutoff_time_saturday', timezone.datetime.strptime('15:00', '%H:%M').time())
        config.cutoff_time_mon = old_time
        config.cutoff_time_tue = old_time
        config.cutoff_time_wed = old_time
        config.cutoff_time_thu = old_time
        config.cutoff_time_fri = old_time
        config.cutoff_time_sat = old_sat
        config.cutoff_time_sun = old_time
        config.save()


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0031_cajaconfig_cutoff_time_saturday'),
    ]

    operations = [
        migrations.AddField(
            model_name='cajaconfig',
            name='cutoff_time_mon',
            field=models.TimeField(default=datetime.time(17, 30), verbose_name='Cutoff Lunes'),
        ),
        migrations.AddField(
            model_name='cajaconfig',
            name='cutoff_time_tue',
            field=models.TimeField(default=datetime.time(17, 30), verbose_name='Cutoff Martes'),
        ),
        migrations.AddField(
            model_name='cajaconfig',
            name='cutoff_time_wed',
            field=models.TimeField(default=datetime.time(17, 30), verbose_name='Cutoff Miércoles'),
        ),
        migrations.AddField(
            model_name='cajaconfig',
            name='cutoff_time_thu',
            field=models.TimeField(default=datetime.time(17, 30), verbose_name='Cutoff Jueves'),
        ),
        migrations.AddField(
            model_name='cajaconfig',
            name='cutoff_time_fri',
            field=models.TimeField(default=datetime.time(17, 30), verbose_name='Cutoff Viernes'),
        ),
        migrations.AddField(
            model_name='cajaconfig',
            name='cutoff_time_sat',
            field=models.TimeField(default=datetime.time(15, 0), verbose_name='Cutoff Sábado'),
        ),
        migrations.AddField(
            model_name='cajaconfig',
            name='cutoff_time_sun',
            field=models.TimeField(default=datetime.time(17, 30), verbose_name='Cutoff Domingo'),
        ),
        migrations.AddField(
            model_name='cashregistersession',
            name='carryover_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Efectivo post-corte (arrastre)'),
        ),
        migrations.RunPython(migrate_cutoff_times),
        migrations.RemoveField(
            model_name='cajaconfig',
            name='cutoff_time',
        ),
        migrations.RemoveField(
            model_name='cajaconfig',
            name='cutoff_time_saturday',
        ),
    ]
