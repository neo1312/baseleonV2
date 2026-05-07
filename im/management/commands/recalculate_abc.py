from django.core.management.base import BaseCommand
from im.abc_calculation import recalculate_abc


class Command(BaseCommand):
    help = 'Manually recalculate ABC inventory classifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Display detailed output'
        )

    def handle(self, *args, **options):
        verbose = options.get('verbose', False)
        
        if verbose:
            self.stdout.write(self.style.SUCCESS('🔄 Starting ABC recalculation...'))
        
        result = recalculate_abc()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ ABC recalculation complete!\n'
                f'   Products updated: {result["products"]}\n'
                f'   Inventory units updated: {result["units"]}'
            )
        )
