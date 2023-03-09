from django.dispatch import receiver
from django.db.models.signals import post_init

from .models import *


@receiver(signal=models.signals.post_init, sender=Account)
def post_init_account_handler(instance, **kwargs):
    instance.original_initial_balance = ftod(instance.initial_balance, 2)
    instance.original_is_balances_valid = instance.is_balances_valid
    instance.original_balances_valid_until = instance.balances_valid_until
    instance.original_type = instance.type


@receiver(signal=models.signals.post_init, sender=BudgetObject)
def post_init_budget_object_handler(instance, **kwargs):
    instance.original_name = instance.name

