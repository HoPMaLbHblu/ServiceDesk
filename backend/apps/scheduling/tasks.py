from celery import shared_task

from . import services


@shared_task(ignore_result=True)
def queue_appointment_reminders() -> int:
    return services.queue_due_reminders()
