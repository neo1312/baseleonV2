from django.db import models


class PrintJob(models.Model):
    """A queued print job for the tablet print bridge (Bluetooth SPP)."""

    JOB_TICKET = 'ticket'
    JOB_LABEL = 'label'
    JOB_TYPES = [
        (JOB_TICKET, 'Ticket'),
        (JOB_LABEL, 'Label'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUSES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
    ]

    job_type = models.CharField(max_length=10, choices=JOB_TYPES, default=JOB_TICKET)
    ticket_type = models.CharField(max_length=20, blank=True, default='')
    ref_id = models.IntegerField(null=True, blank=True)
    value = models.CharField(max_length=255, blank=True, default='')
    copies = models.PositiveIntegerField(default=1)
    blank = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUSES, default=STATUS_PENDING)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.job_type} #{self.pk} [{self.status}]'
