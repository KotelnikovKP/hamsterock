from django.core.paginator import Paginator, EmptyPage
from django.http import HttpResponseRedirect
from django.utils.http import urlencode

from .models import *


def get_u_context(request, initial_context):
    context = initial_context
    context['user'] = request.user
    context['is_authenticated'] = request.user.is_authenticated

    if hasattr(request.user, 'first_name') and hasattr(request.user, 'first_name'):
        context['username'] = request.user.first_name + ' ' + request.user.last_name
        if context['username'] == ' ':
            context['username'] = request.user.username
    context['is_staff'] = request.user.is_staff

    if hasattr(request.user, 'profile'):
        context['avatar'] = request.user.profile.get_url_avatar()

        context['budget'] = request.user.profile.budget
        if request.user.profile.budget:
            context['is_has_budget'] = True

            if request.user.profile.budget.user == request.user:
                context['is_owner_budget'] = True
            else:
                context['is_owner_budget'] = False

            accounts = Account.objects.filter(budget_id=request.user.profile.budget.pk).order_by('name')
            context['accounts'] = accounts

            if accounts:
                context['first_account'] = accounts[0].pk
            else:
                context['first_account'] = 0

            if 'account_selected' not in context:
                context['account_selected'] = 0

            now = datetime.utcnow()
            try:
                first_budget_year = BudgetRegister.objects.filter(budget_id=request.user.profile.budget.pk).order_by('-budget_year')[:1][0].budget_year
                last_budget_year = BudgetRegister.objects.filter(budget_id=request.user.profile.budget.pk).order_by('budget_year')[:1][0].budget_year
            except Exception as e:
                first_budget_year = now.year
                last_budget_year = now.year
            budget_years = [year for year in range(first_budget_year, last_budget_year - 1, -1)]
            if now.month >= request.user.profile.budget.start_budget_month and now.year + 1 not in budget_years:
                budget_years = [now.year + 1] + budget_years
            context['budget_years'] = budget_years
            context['first_budget_year'] = first_budget_year
            if 'budget_year_selected' not in context:
                context['budget_year_selected'] = 0

            base_currencies = [request.user.profile.budget.base_currency_1, request.user.profile.budget.base_currency_2]
            first_base_currency = base_currencies[0].id
            context['base_currencies'] = base_currencies
            context['first_base_currency'] = first_base_currency
            if 'base_currency_selected' not in context:
                context['base_currency_selected'] = 0

            month_shifts = [0, 1]
            context['month_shifts'] = month_shifts
            if 'month_shift_selected' not in context:
                context['month_shift_selected'] = 0

        else:
            context['is_has_budget'] = False
            context['is_owner_budget'] = False

    return context


class SafePaginator(Paginator):
    def validate_number(self, number):
        try:
            return super(SafePaginator, self).validate_number(number)
        except EmptyPage:
            if number > 1:
                return self.num_pages
            else:
                raise


class DataMixin:
    paginator_class = SafePaginator
    paginate_by = 12

    def get_user_context(self, **kwargs):
        return get_u_context(self.request, kwargs)


def custom_redirect(url_name, *args, **kwargs):
    url = reverse(url_name, args=args)
    params = urlencode(kwargs)
    return HttpResponseRedirect(url + "?%s" % params)


def get_execution_percentage(planned_val, actual_val):
    execution_percentage = ftod(0.0000, 4)
    try:
        if planned_val == ftod(0.00, 2) and actual_val == ftod(0.00, 2):
            execution_percentage = ftod(0.0000, 4)
        elif planned_val == ftod(0.00, 2):
            execution_percentage = ftod(9.9999, 4)
        else:
            execution_percentage = ftod(actual_val / planned_val, 4)
    except Exception as e:
        pass
    return execution_percentage

