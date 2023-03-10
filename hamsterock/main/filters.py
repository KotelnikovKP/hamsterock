import django_filters
from django.db.models import Q
from django_filters import DateTimeFromToRangeFilter, RangeFilter, CharFilter
from django_filters.widgets import RangeWidget

from .models import *


def filter_amount_acc_cur_inc(queryset, name, value):
    if value.start and value.stop:
        return queryset.filter(amount_acc_cur__gte=ftod(value.start, 2), amount_acc_cur__lte=ftod(value.stop, 2))
    elif value.start:
        return queryset.filter(amount_acc_cur__gte=ftod(value.start, 2))
    elif value.stop:
        return queryset.filter(amount_acc_cur__gte=ftod(0.00, 2), amount_acc_cur__lte=ftod(value.stop, 2))
    return queryset


def filter_amount_acc_cur_exp(queryset, name, value):
    if value.start and value.stop:
        return queryset.filter(amount_acc_cur__gte=ftod(-value.stop, 2), amount_acc_cur__lte=ftod(-value.start, 2))
    elif value.start:
        return queryset.filter(amount_acc_cur__lte=ftod(-value.start, 2))
    elif value.stop:
        return queryset.filter(amount_acc_cur__gte=ftod(-value.stop, 2), amount_acc_cur__lte=ftod(0.00, 2))
    return queryset


def filter_budget_period(queryset, name, value):
    try:
        budget_year = int(value[:4])
        budget_month = int(value[5:7])
        return queryset.filter(budget_year=budget_year, budget_month=budget_month)
    except:
        return queryset.filter(budget_year=0, budget_month=0)


def filter_description(queryset, name, value):
    return queryset.filter(Q(place__icontains=value) | Q(description__icontains=value))


def filter_banks_description(queryset, name, value):
    return queryset.filter(Q(mcc_code__icontains=value) | Q(banks_category__icontains=value) |
                           Q(banks_description__icontains=value))


def filter_category(queryset, name, value):
    if value.lower() == 'перемещение':
        return queryset.filter(type__icontains='MO')
    elif value.lower() == 'перемещение без связи':
        return queryset.filter(type__icontains='MO', sender__isnull=True, receiver__isnull=True)
    else:
        return queryset.distinct().filter(transaction_categories__category__name__icontains=value)


def filter_project(queryset, name, value):
    return queryset.filter(project__name__icontains=value)


class MyRangeWidget(RangeWidget):
    template_name = "main/account_transaction_multiwidget.html"


class AccountTransactionsFilter(django_filters.FilterSet):
    time_transaction = DateTimeFromToRangeFilter(widget=MyRangeWidget)
    amount_inc = RangeFilter(label='Сумма прихода', method=filter_amount_acc_cur_inc, widget=MyRangeWidget)
    amount_exp = RangeFilter(label='Сумма расхода', method=filter_amount_acc_cur_exp, widget=MyRangeWidget)
    budget_period = CharFilter(label='Период бюджета', method=filter_budget_period)
    description = CharFilter(label='Локация и описание операции', method=filter_description)
    banks_description = CharFilter(label='Информация от банка', method=filter_banks_description)
    category = CharFilter(label='Категория', method=filter_category)
    project = CharFilter(label='Проект', method=filter_project)

    class Meta:
        model = Transaction
        fields = [
            'time_transaction',
            'amount_inc',
            'amount_exp',
            'budget_period',
            'description',
            'banks_description',
            'category',
            'project',
        ]


def filter_account(queryset, name, value):
    return queryset.filter(a_name__icontains=value)


def filter_currency(queryset, name, value):
    return queryset.filter(currency__iso_code__icontains=value)


def filter_amount_inc(queryset, name, value):
    if value.start and value.stop:
        return queryset.filter(amount__gte=ftod(value.start, 2), amount__lte=ftod(value.stop, 2))
    elif value.start:
        return queryset.filter(amount__gte=ftod(value.start, 2))
    elif value.stop:
        return queryset.filter(amount__gte=ftod(0.00, 2), amount__lte=ftod(value.stop, 2))
    return queryset


def filter_amount_exp(queryset, name, value):
    if value.start and value.stop:
        return queryset.filter(amount__gte=ftod(-value.stop, 2), amount__lte=ftod(-value.start, 2))
    elif value.start:
        return queryset.filter(amount__lte=ftod(-value.start, 2))
    elif value.stop:
        return queryset.filter(amount__gte=ftod(-value.stop, 2), amount__lte=ftod(0.00, 2))
    return queryset


class AccountTransactionsFilterForJoin(django_filters.FilterSet):
    time_transaction = DateTimeFromToRangeFilter(widget=MyRangeWidget)
    account = CharFilter(label='Счет/кошелек', method=filter_account)
    amount_acc_cur_inc = RangeFilter(label='Сумма операции в валюте счета', method=filter_amount_acc_cur_inc,
                                     widget=MyRangeWidget)
    amount_acc_cur_exp = RangeFilter(label='Сумма операции в валюте счета', method=filter_amount_acc_cur_exp,
                                     widget=MyRangeWidget)
    currency = CharFilter(label='Валюта операции', method=filter_currency)
    amount_inc = RangeFilter(label='Сумма операции', method=filter_amount_inc, widget=MyRangeWidget)
    amount_exp = RangeFilter(label='Сумма операции', method=filter_amount_exp, widget=MyRangeWidget)
    budget_period = CharFilter(label='Период бюджета', method=filter_budget_period)
    description = CharFilter(label='Локация и описание операции', method=filter_description)
    banks_description = CharFilter(label='Информация от банка', method=filter_banks_description)

    class Meta:
        model = Transaction
        fields = [
            'time_transaction',
            'account',
            'amount_acc_cur_inc',
            'amount_acc_cur_exp',
            'currency',
            'amount_inc',
            'amount_exp',
            'budget_period',
            'description',
            'banks_description',
        ]
