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


@receiver(signal=models.signals.post_init, sender=Transaction)
def post_init_transaction_handler(instance, **kwargs):
    instance.original_time_transaction = instance.time_transaction
    instance.original_amount_acc_cur = ftod(instance.amount_acc_cur, 2)
    instance.original_amount_base_cur_1 = ftod(instance.amount_base_cur_1, 2)
    instance.original_amount_base_cur_2 = ftod(instance.amount_base_cur_2, 2)
    instance.original_budget_year = instance.budget_year
    instance.original_budget_month = instance.budget_month
    instance.original_sender = instance.sender
    instance.original_project = instance.project


@receiver(signal=models.signals.post_init, sender=TransactionCategory)
def post_init_transaction_category_handler(instance, **kwargs):
    instance.original_budget_year = instance.budget_year
    instance.original_budget_month = instance.budget_month
    if hasattr(instance, 'category'):
        instance.original_category = instance.category
    else:
        instance.original_category = None
    instance.original_is_project = 1 if instance.project is not None else 0
    if hasattr(instance, 'project'):
        instance.original_project = instance.project
    else:
        instance.original_project = None
    instance.original_amount_base_cur_1 = ftod(instance.amount_base_cur_1, 2)
    instance.original_amount_base_cur_2 = ftod(instance.amount_base_cur_2, 2)
