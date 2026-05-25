from django.core.management.base import BaseCommand
from im.views.alarm_views import check_alarms


class Command(BaseCommand):
    help = 'Check all enabled alarms and create/update/resolve alarms'

    def handle(self, *args, **options):
        check_alarms()
        self.stdout.write(self.style.SUCCESS('Alarms checked successfully'))
