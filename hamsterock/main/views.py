import csv
import json
from io import StringIO
from uuid import uuid4

from django.contrib.auth import logout, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordChangeDoneView
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction, DataError, IntegrityError
from django.db.models import F, Value, Sum
from django.db.models.functions import Concat
from django.http import HttpResponseNotFound, HttpResponseForbidden, HttpResponseServerError, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import formats, translation
from django.views.generic import FormView, CreateView, UpdateView, DeleteView, ListView
from mptt.utils import tree_item_iterator

from .filters import *
from .forms import *
from .utils import *


def home(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'profile') and not request.user.profile.budget:
            return redirect('start_budget')
        if not Account.objects.filter(budget_id=request.user.profile.budget.pk):
            if request.user.profile.budget.user == request.user:
                return redirect('add_account')
            else:
                return redirect('no_account')
    return render(request, 'main/index.html',
                  get_u_context(request, {'title': 'Хомячок - управление личным бюджетом!',
                                          'selected_menu': 'home',
                                          },))


def about(request):
    return render(request, 'main/about.html',
                  get_u_context(request, {'title': 'О сервисе "Хомячок - управление личным бюджетом!"',
                                          'selected_menu': 'about',
                                          'DEFAULT_BASE_CURRENCY_1': DEFAULT_BASE_CURRENCY_1,
                                          'DEFAULT_BASE_CURRENCY_2': DEFAULT_BASE_CURRENCY_2,
                                          'MIN_BUDGET_YEAR': MIN_BUDGET_YEAR,
                                          'MAX_BUDGET_YEAR': MAX_BUDGET_YEAR,
                                          'DEFAULT_MINUTES_DELTA_FOR_NEW_TRANSACTION':
                                              DEFAULT_MINUTES_DELTA_FOR_NEW_TRANSACTION,
                                          'POSITIVE_EXCHANGE_DIFFERENCE': POSITIVE_EXCHANGE_DIFFERENCE,
                                          'NEGATIVE_EXCHANGE_DIFFERENCE': NEGATIVE_EXCHANGE_DIFFERENCE,
                                          'DEFAULT_INC_CATEGORY': DEFAULT_INC_CATEGORY,
                                          'DEFAULT_EXP_CATEGORY': DEFAULT_EXP_CATEGORY,
                                          },))


def page_not_found(request, exception):
    return HttpResponseNotFound("<h1>Страница не найдена</h1>")


def page_permission_denied(request, exception):
    return HttpResponseForbidden("<h1>Доступ запрещен</h1>")


def page_response_server_error(request):
    return HttpResponseServerError("<h1>Ошибка сервера</h1>")


class ContactFormView(DataMixin, FormView):
    form_class = ContactForm
    template_name = 'main/contact.html'
    success_url = reverse_lazy('home')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context(title='Задай вопрос')
        return dict(list(context.items()) + list(c_def.items()))

    def form_valid(self, form):
        # print(form.cleaned_data)
        return redirect('home')


class LoginUser(DataMixin, LoginView):
    form_class = LoginUserForm
    template_name = 'main/login.html'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context(title='Авторизация', selected_menu='login')
        return dict(list(context.items()) + list(c_def.items()))


def logout_user(request):
    logout(request)
    return redirect('login')


class PasswordChange(DataMixin, PasswordChangeView):
    template_name = 'main/password_change.html'
    success_url = reverse_lazy('password_change_done')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context(title='Смена пароля', profile_menu=True, selected_menu='password_change')
        return dict(list(context.items()) + list(c_def.items()))


class PasswordChangeDone(DataMixin, PasswordChangeDoneView):
    template_name = 'main/password_change_down.html'
    success_url = reverse_lazy('home')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context(title='Пароль был изменён', profile_menu=True,
                                      selected_menu='password_change_down')
        return dict(list(context.items()) + list(c_def.items()))


def register(request):
    """
    Функция регистрации нового пользователя.
    Участвуют в связке три модели: User, Profile, Budget.
    Создается user, также в связке 1:1 profile. При выборе создания нового бюджета создается budget, иначе (при выборе
    присоединения к существующему бюджету) по секретному слову ищется существующий бюджет и указывается в profile
    """
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        profile_form = None
        budget_form = None
        if form.is_valid():
            try:
                with transaction.atomic():
                    new_user = form.save(commit=False)
                    new_user.set_password(form.cleaned_data['password1'])
                    new_user.save()

                    old = request.POST._mutable
                    request.POST._mutable = True
                    request.POST['user'] = str(new_user.pk)
                    if request.POST.get('is_join_to_parent_budget', 'off') != 'on':
                        if request.POST.get('name', '') == DEFAULT_BUDGET_NAME:
                            if request.POST.get('last_name', '') != '':
                                request.POST['name'] = 'Бюджет семьи ' + str(request.POST.get('last_name', ''))
                            else:
                                if request.POST.get('first_name', '') != '':
                                    request.POST['name'] = 'Бюджет семьи ' + str(request.POST.get('first_name', ''))
                                else:
                                    request.POST['name'] = 'Бюджет семьи ' + str(request.POST.get('username', ''))
                    request.POST._mutable = old

                    budget_form = BudgetRegistrationForm(data=request.POST, files=request.FILES)
                    if request.POST.get('is_join_to_parent_budget', 'off') == 'on':
                        # Пытаемся найти существующий бюджет
                        new_budget = Budget.objects.get(secret_key=request.POST.get('secret_key', None))
                    else:
                        # Создаем новый бюджет
                        if budget_form.is_valid():
                            new_budget = budget_form.save(commit=False)
                            new_budget.secret_key = 'HSK-' + str(uuid4()).replace('-', '')[::2]
                            new_budget.save()
                        else:
                            raise DataError

                    old = request.POST._mutable
                    request.POST._mutable = True
                    request.POST['budget'] = str(new_budget.pk)
                    request.POST._mutable = old

                    profile_form = ProfileRegistrationForm(data=request.POST, files=request.FILES)
                    if profile_form.is_valid():
                        profile_form.save()
                        login(request, new_user)
                        return redirect('home')
                    else:
                        raise IntegrityError

            except IntegrityError:
                profile_form.add_error(None, profile_form['user'].errors)
            except DataError:
                profile_form.add_error(None, 'Ошибка сохранения нового бюджета')
            except (ObjectDoesNotExist, MultipleObjectsReturned):
                budget_form.add_error('secret_key', 'Секретное слово не верно!')
            except Exception:
                form.add_error(None, 'Ошибка сохранения')
            finally:
                if not budget_form:
                    budget_form = BudgetRegistrationForm(data=request.POST, files=request.FILES)
                if not profile_form:
                    profile_form = ProfileRegistrationForm(data=request.POST, files=request.FILES)
        else:
            budget_form = BudgetRegistrationForm(data=request.POST, files=request.FILES)
            profile_form = ProfileRegistrationForm(data=request.POST, files=request.FILES)
    else:
        form = UserRegistrationForm()
        profile_form = ProfileRegistrationForm()
        budget_form = BudgetRegistrationForm(initial={'name': DEFAULT_BUDGET_NAME,
                                                      'base_currency_1': DEFAULT_BASE_CURRENCY_1,
                                                      'base_currency_2': DEFAULT_BASE_CURRENCY_2,
                                                      }
                                             )
    return render(request, 'main/user_register.html', get_u_context(request, {'title': 'Регистрация',
                                                                              'form': form,
                                                                              'profile_form': profile_form,
                                                                              'budget_form': budget_form,
                                                                              'selected_menu': 'register'}))


@login_required
def edit_user(request):
    """
    Функция изменения пользователя.
    Участвуют две модели User и Profile
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        old = request.POST._mutable
        request.POST._mutable = True
        request.POST['username'] = str(request.user.username)
        request.POST._mutable = old
        user_form = UserEditForm(instance=request.user, data=request.POST)
        profile_form = ProfileEditForm(instance=request.user.profile, data=request.POST, files=request.FILES)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            return redirect('edit_user')
    else:
        if not hasattr(request.user, 'profile'):
            Profile.objects.create(user=request.user)
        user_form = UserEditForm(instance=request.user)
        profile_form = ProfileEditForm(instance=request.user.profile)
    return render(request, 'main/user_edit.html', get_u_context(request, {'title': 'Профиль пользователя',
                                                                          'user_form': user_form,
                                                                          'profile_form': profile_form,
                                                                          'profile_menu': True,
                                                                          'selected_menu': 'edit_user'}))


@login_required
def start_budget(request):
    """
    Функция старта бюджета
    Пользователь может стартовать новый бюджет или присоединиться к существующему, если перед этим удалил свой бюджет
    как владелец, или вышел из бюджета, к которому ранее присоединился
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        profile_form = None
        budget_form = None
        try:
            with transaction.atomic():
                old = request.POST._mutable
                request.POST._mutable = True
                request.POST['user'] = str(request.user.pk)
                if request.POST.get('is_join_to_parent_budget', 'off') != 'on':
                    if request.POST.get('name', '') == DEFAULT_BUDGET_NAME:
                        if request.user.last_name != '':
                            request.POST['name'] = 'Бюджет семьи ' + request.user.last_name
                        else:
                            if request.user.first_name != '':
                                request.POST['name'] = 'Бюджет семьи ' + request.user.first_name
                            else:
                                request.POST['name'] = 'Бюджет семьи ' + request.user.username
                request.POST._mutable = old

                budget_form = BudgetStartBudgetForm(data=request.POST, files=request.FILES)
                if request.POST.get('is_join_to_parent_budget', 'off') == 'on':
                    # Пытаемся найти существующий бюджет
                    new_budget = Budget.objects.get(secret_key=request.POST.get('secret_key', None))
                else:
                    # Создаем новый бюджет
                    if budget_form.is_valid():
                        new_budget = budget_form.save(commit=False)
                        new_budget.secret_key = 'HSK-' + str(uuid4()).replace('-', '')[::2]
                        new_budget.save()
                    else:
                        raise DataError

                old = request.POST._mutable
                request.POST._mutable = True
                request.POST['budget'] = str(new_budget.pk)
                request.POST._mutable = old

                profile_form = ProfileStartBudgetForm(instance=request.user.profile, data=request.POST,
                                                      files=request.FILES)
                if profile_form.is_valid():
                    profile_form.save()
                    return redirect('home')
                else:
                    raise IntegrityError

        except IntegrityError:
            budget_form.add_error(None, budget_form['user'].errors)
        except DataError:
            budget_form.add_error(None, 'Ошибка сохранения нового бюджета')
        except (ObjectDoesNotExist, MultipleObjectsReturned):
            budget_form.add_error('secret_key', 'Секретное слово не верно!')
        except Exception:
            budget_form.add_error(None, 'Ошибка сохранения')
        finally:
            if not budget_form:
                budget_form = BudgetStartBudgetForm(data=request.POST, files=request.FILES)
            if not profile_form:
                profile_form = ProfileStartBudgetForm(instance=request.user.profile, data=request.POST,
                                                      files=request.FILES)
    else:
        if not hasattr(request.user, 'profile'):
            Profile.objects.create(user=request.user)
        profile_form = ProfileStartBudgetForm(instance=request.user.profile)
        budget_form = BudgetStartBudgetForm(initial={'name': DEFAULT_BUDGET_NAME,
                                                     'base_currency_1': DEFAULT_BASE_CURRENCY_1,
                                                     'base_currency_2': DEFAULT_BASE_CURRENCY_2,
                                                     }
                                            )
    return render(request, 'main/budget_start.html', get_u_context(request, {'title': 'Начать вести бюджет',
                                                                             'profile_form': profile_form,
                                                                             'budget_form': budget_form,
                                                                             'profile_menu': True,
                                                                             'selected_menu': 'start_budget'}))


@login_required
def edit_budget(request):
    """
    Функция изменения текущего бюджета
    Доступна только владельцу бюджета.
    Изменяются параметры бюджета:
    - название бюджета;
    - секретное слово для присоединения к бюджету других пользователей;
    - округление плановых значений;
    - месяц начала планирования бюджета следующего года;
    - Месяц окончания планирования бюджета текущего года.
    Базовую и дополнительные валюты бюджета изменять нельзя, они задаются только при старте бюджета (в функции
    регистрации пользователя или в функции старта бюджета)
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    if request.user.profile.budget.user != request.user:
        return redirect('home')

    if request.method == 'POST':
        form = BudgetEditForm(instance=request.user.profile.budget, data=request.POST)
        if form.is_valid():
            form.save()
            return redirect('edit_budget')
    else:
        form = BudgetEditForm(instance=request.user.profile.budget,
                              initial={'base_currency_1': request.user.profile.budget.base_currency_1,
                                       'base_currency_2': request.user.profile.budget.base_currency_2,
                                       }
                              )
    return render(request, 'main/budget_edit.html', get_u_context(request, {'title': 'Настройки бюджета',
                                                                            'form': form,
                                                                            'profile_menu': True,
                                                                            'selected_menu': 'edit_budget'}))


@login_required
def show_budget(request):
    """
    Функция просмотра параметров бюджета
    Доступна присоединившимся к бюджету пользователям.
    Позволяет просмотреть параметры, но не изменять
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    if request.user.profile.budget.user.first_name or request.user.profile.budget.user.last_name:
        owner = request.user.profile.budget.user.first_name + ' ' + request.user.profile.budget.user.last_name
    else:
        owner = request.user.profile.budget.user.username
    digit_rounding = ''
    for dr in ROUNDING:
        if dr[0] == request.user.profile.budget.digit_rounding:
            digit_rounding = dr[1]
            break
    start_budget_month = ''
    for sbm in MONTHS:
        if sbm[0] == request.user.profile.budget.start_budget_month:
            start_budget_month = sbm[1]
            break
    end_budget_month = ''
    for sbm in MONTHS:
        if sbm[0] == request.user.profile.budget.end_budget_month:
            end_budget_month = sbm[1]
            break
    form = BudgetShowForm(initial={'name': request.user.profile.budget.name,
                                   'user': owner,
                                   'digit_rounding': digit_rounding,
                                   'start_budget_month': start_budget_month,
                                   'end_budget_month': end_budget_month,
                                   'base_currency_1': request.user.profile.budget.base_currency_1,
                                   'base_currency_2': request.user.profile.budget.base_currency_2,
                                   }
                          )
    return render(request, 'main/budget_view.html', get_u_context(request, {'title': 'Настройки бюджета',
                                                                            'form': form,
                                                                            'profile_menu': True,
                                                                            'selected_menu': 'show_budget'}))


@login_required
def budget_users(request):
    """
    Функция просмотра и изменения списка пользователей бюджета
    Доступна только владельцу бюджета.
    Выводится список пользователей, есть возможность отключить от бюджета присоединившегося пользователя
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    if request.user.profile.budget.user != request.user:
        return redirect('home')
    title = 'Пользователи бюджета - ' + request.user.profile.budget.name
    list_users = User.objects.filter(profile__budget__id=request.user.profile.budget.pk)
    return render(request, 'main/budget_users.html', get_u_context(request, {'title': title,
                                                                             'list_users': list_users,
                                                                             'owner': request.user,
                                                                             'profile_menu': True,
                                                                             'selected_menu': 'budget_users'}))


@login_required
def remove_user_from_budget(request, user_id, return_url):
    """
    Функция отключения пользователя от бюджета.
    Отключиться от бюджета пользователь может самостоятельно, либо его может отключить владелец бюджета.
    После отключения от бюджета пользователь может стартовать новый бюджет, либо присоединиться к существующему по
    секретному коду
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    removed_user = get_object_or_404(User, pk=user_id)
    if removed_user.profile.budget != request.user.profile.budget:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")

    if return_url[0:1] != '/':
        return_url = '/' + return_url
    if removed_user.first_name or removed_user.last_name:
        removed_user_name = removed_user.first_name + ' ' + removed_user.last_name
    else:
        removed_user_name = removed_user.username
    budget_owner = removed_user.profile.budget.user
    if budget_owner.first_name or budget_owner.last_name:
        budget_owner_name = budget_owner.first_name + ' ' + budget_owner.last_name
    else:
        budget_owner_name = budget_owner.username
    budget_name = removed_user.profile.budget.name
    if removed_user == budget_owner:
        title = 'Подтверждение удаления бюджета - ' + budget_name
    else:
        title = 'Подтверждение отключения ' + removed_user_name + ' от ' + budget_name
    if request.method == 'POST':
        removed_user.profile.budget = None
        removed_user.profile.save()
        return redirect(return_url)
    else:
        form = RemoveUserFromBudgetForm()
    return render(request, 'main/budget_remove_user.html',
                  get_u_context(request, {'title': title,
                                          'removed_user': removed_user,
                                          'removed_user_name': removed_user_name,
                                          'budget_owner': budget_owner,
                                          'budget_owner_name': budget_owner_name,
                                          'budget_name': budget_name,
                                          'form': form,
                                          'profile_menu': True,
                                          'selected_menu': 'remove_user_from_budget'
                                          }))


@login_required
def no_account(request):
    """
    Функция сообщения об отсутствии счетов в бюджете пользователю, который присоединился к бюджету другого пользователя
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    budget_owner = request.user.profile.budget.user
    if budget_owner.first_name or budget_owner.last_name:
        budget_owner_name = budget_owner.first_name + ' ' + budget_owner.last_name
    else:
        budget_owner_name = budget_owner.username
    budget_name = request.user.profile.budget.name
    return render(request, 'main/account_does_not_exist.html',
                  get_u_context(request, {'title': 'Добавление первого счета/кошелька',
                                          'budget_owner_name': budget_owner_name,
                                          'budget_name': budget_name}))


class AddAccount(LoginRequiredMixin, DataMixin, CreateView):
    """
    Класс добавления счета/кошелька в бюджет
    Доступен только для владельца бюджета
    """
    form_class = AddAccountForm
    template_name = 'main/account_add.html'
    login_url = reverse_lazy('login')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context(title='Добавление счета/кошелька',
                                      work_menu=True,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def get_success_url(self):
        return reverse_lazy('account_transactions', kwargs={'account_id': self.object.pk})

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.user = self.request.user
        self.object.budget = self.request.user.profile.budget
        return super(AddAccount, self).form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if request.user.profile.budget.user != request.user:
                return self.handle_no_permission()
        self.initial = {'time_zone': ftod(self.request.user.profile.time_zone, 2)}
        return super(AddAccount, self).dispatch(request, *args, **kwargs)


class EditAccount(LoginRequiredMixin, DataMixin, UpdateView):
    """
    Класс изменения счета/кошелька бюджета
    Доступен только для владельца бюджета
    """
    form_class = EditAccountForm
    model = Account
    template_name = 'main/account_edit.html'
    pk_url_kwarg = 'account_id'
    login_url = reverse_lazy('login')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        a = get_object_or_404(Account, pk=self.kwargs['account_id'])
        c_def = self.get_user_context(title='Редактирование счета/кошелька - ' + str(a.name) + ' (' +
                                            str(a.currency.iso_code) + ')',
                                      account_selected=a.id,
                                      account_currency=a.currency.iso_code,
                                      work_menu=True,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def get_success_url(self):
        return reverse_lazy('account_transactions', kwargs={'account_id': self.kwargs['account_id']})

    def dispatch(self, request, *args, **kwargs):
        a = get_object_or_404(Account, pk=self.kwargs['account_id'])
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if request.user.profile.budget.user != request.user:
                return self.handle_no_permission()
            if a.budget != request.user.profile.budget:
                return self.handle_no_permission()
        return super(EditAccount, self).dispatch(request, *args, **kwargs)


class DeleteAccount(LoginRequiredMixin, DataMixin, DeleteView):
    """
    Класс удаления счета/кошелька бюджета
    Доступен только для владельца бюджета
    """
    model = Account
    template_name = 'main/account_delete.html'
    pk_url_kwarg = 'account_id'
    success_url = reverse_lazy('home')
    login_url = reverse_lazy('login')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        a = get_object_or_404(Account, pk=self.kwargs['account_id'])
        c_def = self.get_user_context(title='Удаление счета/кошелька - ' + str(a.name) + ' (' +
                                            str(a.currency.iso_code) + ')',
                                      account_selected=a.id,
                                      account=a,
                                      work_menu=True,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def form_valid(self, form):
        a = self.get_object()
        # Если есть операции по счету, то удалять счет нельзя
        if Transaction.objects.filter(account_id=a.pk).count() > 0:
            return render(self.request, 'main/account_delete.html',
                          get_u_context(self.request, {'title': 'Удаление счета/кошелька - ' + str(a.name) + ' (' +
                                                                str(a.currency.iso_code) + ')',
                                                       'account_selected': a.id,
                                                       'account': a,
                                                       'error_message': 'Нельзя удалить счет/кошелек - в систему '
                                                                        'заведены операции по нему',
                                                       'work_menu': True,
                                                       'selected_menu': 'account_transactions'}))

        return super(DeleteAccount, self).form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        a = get_object_or_404(Account, pk=self.kwargs['account_id'])
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if request.user.profile.budget.user != request.user:
                return self.handle_no_permission()
            if a.budget != request.user.profile.budget:
                return self.handle_no_permission()
        return super(DeleteAccount, self).dispatch(request, *args, **kwargs)


class Projects(LoginRequiredMixin, DataMixin, ListView):
    """
    Класс вывода списка проектов бюджета
    """
    model = Project
    template_name = 'main/projects.html'
    context_object_name = 'projects'
    allow_empty = True

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context(title='Проекты',
                                      work_menu=True,
                                      account_selected=-1,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def get_queryset(self):
        if not self.request.user.profile.budget:
            b_id = 0
        else:
            b_id = self.request.user.profile.budget.pk
        return Project.objects.filter(budget_id=b_id)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
        return super(Projects, self).dispatch(request, *args, **kwargs)


class AddProject(LoginRequiredMixin, DataMixin, CreateView):
    """
    Класс добавления проекта в бюджет
    """
    form_class = AddProjectForm
    template_name = 'main/project_add.html'
    login_url = reverse_lazy('login')
    success_url = reverse_lazy('projects')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context(title='Добавление проекта',
                                      work_menu=True,
                                      account_selected=-1,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def form_valid(self, form):
        if Project.objects.filter(budget_id=self.request.user.profile.budget, name=form.cleaned_data['name']):
            form.add_error('name', forms.ValidationError('Проект с таким именем уже существует!'))
            return self.render_to_response(self.get_context_data(form=form))
        self.object = form.save(commit=False)
        self.object.budget = self.request.user.profile.budget
        return super(AddProject, self).form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
        return super(AddProject, self).dispatch(request, *args, **kwargs)


class EditProject(LoginRequiredMixin, DataMixin, UpdateView):
    """
    Класс изменения проекта бюджета
    """
    form_class = EditProjectForm
    model = Project
    template_name = 'main/project_edit.html'
    pk_url_kwarg = 'project_id'
    login_url = reverse_lazy('login')
    success_url = reverse_lazy('projects')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        p = get_object_or_404(Project, pk=self.kwargs['project_id'])
        c_def = self.get_user_context(title='Редактирование проекта - ' + str(p.name),
                                      account_selected=-1,
                                      work_menu=True,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def dispatch(self, request, *args, **kwargs):
        p = get_object_or_404(Project, pk=self.kwargs['project_id'])
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if p.budget != request.user.profile.budget:
                return self.handle_no_permission()
        return super(EditProject, self).dispatch(request, *args, **kwargs)


class DeleteProject(LoginRequiredMixin, DataMixin, DeleteView):
    """
    Класс удаления проекта бюджета
    """
    model = Project
    template_name = 'main/project_delete.html'
    pk_url_kwarg = 'project_id'
    success_url = reverse_lazy('projects')
    login_url = reverse_lazy('login')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        p = get_object_or_404(Project, pk=self.kwargs['project_id'])
        c_def = self.get_user_context(title='Удаление проекта - ' + str(p.name),
                                      account_selected=-1,
                                      project=p,
                                      work_menu=True,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def form_valid(self, form):
        p = self.get_object()
        # Если есть операции с текущим проектом, то удалять его нельзя
        if Transaction.objects.filter(project_id=p.pk).count() > 0:
            return render(self.request, 'main/project_delete.html',
                          get_u_context(self.request, {'title': 'Удаление проекта - ' + str(p.name),
                                                       'account_selected': -1,
                                                       'project': p,
                                                       'error_message': 'Нельзя удалить проект - в систему '
                                                                        'заведены операции по нему',
                                                       'work_menu': True,
                                                       'selected_menu': 'account_transactions'}))

        return super(DeleteProject, self).form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        p = get_object_or_404(Project, pk=self.kwargs['project_id'])
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if p.budget != request.user.profile.budget:
                return self.handle_no_permission()
        # print(p)
        return super(DeleteProject, self).dispatch(request, *args, **kwargs)


class BudgetObjects(LoginRequiredMixin, DataMixin, ListView):
    """
    Класс вывода списка бюджетных объектов
    """
    model = BudgetObject
    template_name = 'main/budget_objects.html'
    context_object_name = 'budget_objects'
    allow_empty = True

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context(title='Объекты бюджета',
                                      work_menu=True,
                                      account_selected=-2,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def get_queryset(self):
        if not self.request.user.profile.budget:
            b_id = 0
        else:
            b_id = self.request.user.profile.budget.pk
        return BudgetObject.objects.filter(budget_id=b_id)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
        return super(BudgetObjects, self).dispatch(request, *args, **kwargs)


class AddBudgetObject(LoginRequiredMixin, DataMixin, CreateView):
    """
    Класс добавления бюджетного объекта
    """
    form_class = AddBudgetObjectForm
    template_name = 'main/budget_object_add.html'
    login_url = reverse_lazy('login')
    success_url = reverse_lazy('budget_objects')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        c_def = self.get_user_context(title='Добавление объекта бюджета',
                                      work_menu=True,
                                      account_selected=-2,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def form_valid(self, form):
        if BudgetObject.objects.filter(budget_id=self.request.user.profile.budget, name=form.cleaned_data['name']):
            form.add_error('name', forms.ValidationError('Объект бюджета с таким именем уже существует!'))
            return self.render_to_response(self.get_context_data(form=form))
        self.object = form.save(commit=False)
        self.object.budget = self.request.user.profile.budget
        return super(AddBudgetObject, self).form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
        return super(AddBudgetObject, self).dispatch(request, *args, **kwargs)


class EditBudgetObject(LoginRequiredMixin, DataMixin, UpdateView):
    """
    Класс изменения бюджетного объекта
    """
    form_class = EditBudgetObjectForm
    model = BudgetObject
    template_name = 'main/budget_object_edit.html'
    pk_url_kwarg = 'budget_object_id'
    login_url = reverse_lazy('login')
    success_url = reverse_lazy('budget_objects')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        b = get_object_or_404(BudgetObject, pk=self.kwargs['budget_object_id'])
        c_def = self.get_user_context(title='Редактирование объекта бюджета - ' + str(b.name),
                                      account_selected=-2,
                                      work_menu=True,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def dispatch(self, request, *args, **kwargs):
        b = get_object_or_404(BudgetObject, pk=self.kwargs['budget_object_id'])
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if b.budget != request.user.profile.budget:
                return self.handle_no_permission()
        return super(EditBudgetObject, self).dispatch(request, *args, **kwargs)


class DeleteBudgetObject(LoginRequiredMixin, DataMixin, DeleteView):
    """
    Класс удаления бюджетного объекта
    """
    model = BudgetObject
    template_name = 'main/budget_object_delete.html'
    pk_url_kwarg = 'budget_object_id'
    success_url = reverse_lazy('budget_objects')
    login_url = reverse_lazy('login')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        b = get_object_or_404(BudgetObject, pk=self.kwargs['budget_object_id'])
        c_def = self.get_user_context(title='Удаление объекта бюджета - ' + str(b.name),
                                      account_selected=-2,
                                      budget_object=b,
                                      work_menu=True,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def form_valid(self, form):
        b = self.get_object()
        categories = Category.objects.filter(budget_object_id=b.pk)
        is_transactions_exist = False
        for category in categories:
            # Если есть категории с бюджетным объектом в операциях, то удалять бюджетный объект нельзя
            if TransactionCategory.objects.filter(category_id=category.pk).count() > 0:
                is_transactions_exist = True
                break
        if is_transactions_exist:
            return render(self.request, 'main/budget_object_delete.html',
                          get_u_context(self.request, {'title': 'Удаление объекта бюджета - ' + str(b.name),
                                                       'account_selected': -2,
                                                       'budget_object': b,
                                                       'error_message': 'Нельзя удалить объекта бюджета - в систему '
                                                                        'заведены операции по нему',
                                                       'work_menu': True,
                                                       'selected_menu': 'account_transactions'}))

        return super(DeleteBudgetObject, self).form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        b = get_object_or_404(BudgetObject, pk=self.kwargs['budget_object_id'])
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if b.budget != request.user.profile.budget:
                return self.handle_no_permission()
        # print(p)
        return super(DeleteBudgetObject, self).dispatch(request, *args, **kwargs)


class AccountTransactions(LoginRequiredMixin, DataMixin, ListView):
    """
    Класс списка операций по счету
    """
    model = Transaction
    template_name = 'main/account_transactions.html'
    context_object_name = 'transactions'
    allow_empty = True
    account_transaction_filter = None

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        a = get_object_or_404(Account, pk=self.kwargs['account_id'])
        c_def = self.get_user_context(title='Операции по счету/кошельку - ' + str(a),
                                      filter=self.account_transaction_filter,
                                      account_selected=a.id,
                                      account_currency_id=a.currency.id,
                                      account_currency_iso=a.currency.iso_code,
                                      account_available_balance=a.balance + a.credit_limit,
                                      account_balance=a.balance,
                                      account_credit_limit=a.credit_limit,
                                      account_type=a.type,
                                      account_budget=a.budget.id,
                                      work_menu=True,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def dispatch(self, request, *args, **kwargs):
        a = get_object_or_404(Account, pk=self.kwargs['account_id'])
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if a.budget != request.user.profile.budget:
                return self.handle_no_permission()
        if not self.request.user.profile.budget:
            b_id = 0
        else:
            b_id = self.request.user.profile.budget.pk

        self.account_transaction_filter = \
            AccountTransactionsFilter(
                request.GET, request=request,
                queryset=Transaction.objects.filter(budget_id=b_id, account_id=self.kwargs['account_id']).exclude(
                    type__in=['ED+', 'ED-']).select_related('budget', 'account', 'currency', 'sender')
            )
        self.queryset = self.account_transaction_filter.qs
        return super(AccountTransactions, self).dispatch(request, *args, **kwargs)


@login_required
def add_transaction(request, account_id, return_url):
    """
    Функция добавления операции.
    Участвуют две модели Transaction и TransactionCategory.
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')

    a = get_object_or_404(Account, pk=account_id)

    if a.budget != request.user.profile.budget:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")

    if return_url[0:1] != '/':
        return_url = '/' + return_url

    if request.method == 'POST':
        datetime_formats = formats.get_format("DATETIME_INPUT_FORMATS", lang=translation.get_language())
        datetime_formats.append(datetime_formats[0][:8])
        example_datetime = datetime.utcnow()
        valid_datetime_formats = 'Допустимые форматы даты-времени:'
        for datetime_format in datetime_formats:
            valid_datetime_formats += f" {datetime_format}: {example_datetime.strftime(datetime_format)};"

        old = request.POST._mutable
        request.POST._mutable = True
        request.POST['budget'] = str(a.budget.pk)
        request.POST['account'] = str(a.pk)
        request.POST['user_create'] = str(request.user.pk)
        request.POST['user_update'] = str(request.user.pk)
        is_time_transaction_error = True
        for datetime_format in datetime_formats:
            try:
                time_transaction_from_post = datetime.strptime(request.POST['form_time_transaction'], datetime_format)
                if time_transaction_from_post.hour != 0 or time_transaction_from_post.minute != 0 or \
                        time_transaction_from_post.second != 0 or time_transaction_from_post.microsecond != 0:
                    request.POST['time_transaction'] = \
                        (time_transaction_from_post - timedelta(hours=float(request.POST['time_zone']))
                         ).strftime(formats.get_format("DATETIME_INPUT_FORMATS", lang=translation.get_language())[0])
                else:
                    request.POST['time_transaction'] = request.POST['form_time_transaction']
                is_time_transaction_error = False
                break
            except Exception as e:
                pass
        if is_time_transaction_error:
            request.POST['time_transaction'] = request.POST['form_time_transaction']

        if request.POST['type'] in ['DEB', 'MO-']:
            request.POST['amount'] = \
                request.POST['amount'][1:] \
                if request.POST['amount'][0] == '-' \
                else '-' + request.POST['amount']
            request.POST['amount_acc_cur'] = \
                request.POST['amount_acc_cur'][1:] \
                if request.POST['amount_acc_cur'][0] == '-' \
                else '-' + request.POST['amount_acc_cur']
        if request.POST['currency'] == str(a.currency.pk):
            request.POST['amount'] = request.POST['amount_acc_cur']
        request.POST._mutable = old
        form = TransactionAddForm(budget_id=a.budget.pk, data=request.POST)
        category_form = None
        if is_time_transaction_error:
            form.add_error('form_time_transaction', 'datetime_error')
        if form.is_valid():
            if request.POST['type'] in ['MO+', 'MO-']:
                try:
                    with transaction.atomic():
                        form.save()
                        return redirect(return_url)
                except Exception as e:
                    form.add_error(None, 'Что-то пошло не так с добавлением операции - ' + str(e))
            else:
                try:
                    with transaction.atomic():
                        new_transaction = form.save()

                        old = request.POST._mutable
                        request.POST._mutable = True
                        request.POST['transaction'] = str(new_transaction.pk)

                        if request.POST['type'] == 'CRE':
                            request.POST['category'] = Category.get_category_with_object(a.budget,
                                                                                         request.POST['category_inc'],
                                                                                         request.POST['budget_object'],
                                                                                         request.user)
                            request.POST['category_exp'] = ''
                        elif request.POST['type'] == 'DEB':
                            request.POST['category'] = Category.get_category_with_object(a.budget,
                                                                                         request.POST['category_exp'],
                                                                                         request.POST['budget_object'],
                                                                                         request.user)
                            request.POST['category_inc'] = ''
                        else:
                            request.POST['category'] = ''
                        request.POST._mutable = old

                        category_form = TransactionCategoryAddForm(budget_id=a.budget.pk, data=request.POST)

                        if request.POST['category'] == '' and \
                                (request.POST['type'] == 'CRE' or request.POST['type'] == 'DEB'):
                            raise ValidationError('Выберите категорию!')

                        if category_form.is_valid():
                            category_form.save()
                            return redirect(return_url)
                        else:
                            raise IntegrityError

                except IntegrityError:
                    pass
                except ValidationError:
                    if request.POST['type'] == 'CRE':
                        category_form.add_error('category_inc', 'Выберите категорию!')
                    elif request.POST['type'] == 'DEB':
                        category_form.add_error('category_exp', 'Выберите категорию!')
                except Exception as e:
                    form.add_error(None, 'Что-то пошло не так с добавлением операции - ' + str(e))

                old = request.POST._mutable
                request.POST._mutable = True
                if request.POST['type'] in ['DEB', 'MO-']:
                    request.POST['amount'] = \
                        request.POST['amount'][1:] \
                        if request.POST['amount'][0] == '-' \
                        else '-' + request.POST['amount']
                    request.POST['amount_acc_cur'] = \
                        request.POST['amount_acc_cur'][1:] \
                        if request.POST['amount_acc_cur'][0] == '-' \
                        else '-' + request.POST['amount_acc_cur']
                if request.POST['currency'] == str(a.currency.pk):
                    request.POST['amount'] = request.POST['amount_acc_cur']
                request.POST._mutable = old
                form = TransactionAddForm(budget_id=a.budget.pk, data=request.POST)
                if not category_form:
                    category_form = TransactionCategoryAddForm(budget_id=a.budget.pk, data=request.POST)
        else:
            old = request.POST._mutable
            request.POST._mutable = True
            if request.POST['type'] in ['DEB', 'MO-']:
                request.POST['amount'] = \
                    request.POST['amount'][1:] \
                    if request.POST['amount'][0] == '-' \
                    else '-' + request.POST['amount']
                request.POST['amount_acc_cur'] = \
                    request.POST['amount_acc_cur'][1:] \
                    if request.POST['amount_acc_cur'][0] == '-' \
                    else '-' + request.POST['amount_acc_cur']
            if request.POST['currency'] == str(a.currency.pk):
                request.POST['amount'] = request.POST['amount_acc_cur']
            request.POST._mutable = old
            form = TransactionAddForm(budget_id=a.budget.pk, data=request.POST)
            category_form = TransactionCategoryAddForm(budget_id=a.budget.pk, data=request.POST)
            if is_time_transaction_error:
                form.add_error('form_time_transaction', valid_datetime_formats)
    else:
        form = TransactionAddForm(budget_id=a.budget.pk,
                                  initial={'type': 'DEB',
                                           'form_time_transaction':
                                               datetime.utcnow() + timedelta(hours=float(a.time_zone)),
                                           'time_zone': a.time_zone,
                                           'currency': a.currency,
                                           'budget_year': datetime.utcnow().year,
                                           'budget_month': datetime.utcnow().month,
                                           },
                                  )
        category_form = TransactionCategoryAddForm(budget_id=a.budget.pk)

    return render(request, 'main/transaction_add.html',
                  get_u_context(request,
                                {'title': 'Добавление операции',
                                 'form': form,
                                 'category_form': category_form,
                                 'account_selected': a.id,
                                 'account_currency': a.currency.iso_code,
                                 'account_currency_id': a.currency.pk,
                                 'is_account_not_cash': a.type not in ALL_CASH_ACCOUNT,
                                 'work_menu': True,
                                 'selected_menu': 'account_transactions',
                                 'return_url': return_url}))


@login_required
def edit_transaction(request, transaction_id, return_url):
    """
    Функция изменения операции
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')

    t = get_object_or_404(Transaction, pk=transaction_id)

    if t.budget != request.user.profile.budget:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")

    if return_url[0:1] != '/':
        return_url = '/' + return_url

    transaction_name = str(t)

    rec = None
    if t.type == 'MO-':
        try:
            rec = t.receiver
        except Exception as e:
            rec = None

    is_linked_movement = t.type == 'MO+' and t.sender or t.type == 'MO-' and rec

    if request.method == 'POST':
        is_time_transaction_error = False

        old = request.POST._mutable
        request.POST._mutable = True
        request.POST['user_update'] = request.user

        valid_datetime_formats = 'Допустимые форматы даты-времени:'
        if request.POST.get('form_time_transaction'):
            datetime_formats = formats.get_format("DATETIME_INPUT_FORMATS", lang=translation.get_language())
            datetime_formats.append(datetime_formats[0][:8])
            example_datetime = datetime.utcnow()
            for datetime_format in datetime_formats:
                valid_datetime_formats += f" {datetime_format}: {example_datetime.strftime(datetime_format)};"

            is_time_transaction_error = True
            for datetime_format in datetime_formats:
                try:
                    time_transaction_from_post = datetime.strptime(request.POST['form_time_transaction'],
                                                                   datetime_format)
                    if time_transaction_from_post.hour != 0 or time_transaction_from_post.minute != 0 or \
                            time_transaction_from_post.second != 0 or time_transaction_from_post.microsecond != 0:
                        request.POST['time_transaction'] = \
                            (time_transaction_from_post - timedelta(hours=float(request.POST['time_zone']))
                             ).strftime(
                                formats.get_format("DATETIME_INPUT_FORMATS", lang=translation.get_language())[0])
                    else:
                        request.POST['time_transaction'] = request.POST['form_time_transaction']
                    is_time_transaction_error = False
                    break
                except Exception as e:
                    pass
            if is_time_transaction_error:
                request.POST['time_transaction'] = request.POST['form_time_transaction']

        if not is_linked_movement:
            if t.type in ['DEB', 'MO-']:
                request.POST['amount'] = \
                    request.POST['amount'][1:] \
                    if request.POST['amount'][0] == '-' \
                    else '-' + request.POST['amount']
                request.POST['amount_acc_cur'] = \
                    request.POST['amount_acc_cur'][1:] \
                    if request.POST['amount_acc_cur'][0] == '-' \
                    else '-' + request.POST['amount_acc_cur']
            if request.POST['currency'] == str(t.account.currency.id):
                request.POST['amount'] = request.POST['amount_acc_cur']
        else:
            if t.type in ['DEB', 'MO-']:
                t.amount_acc_cur = -t.amount_acc_cur
                t.amount = -t.amount
        request.POST._mutable = old

        form = TransactionEditForm(budget_id=t.budget.pk, is_linked_movement=is_linked_movement, instance=t,
                                   data=request.POST)
        if is_time_transaction_error:
            form.add_error('form_time_transaction', 'datetime_error')

        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
                    return redirect(return_url)

            except Exception as e:
                form.add_error(None, 'Что-то пошло не так с изменением операции - ' + str(e))

        old = request.POST._mutable
        request.POST._mutable = True
        if not is_linked_movement:
            if t.type in ['DEB', 'MO-']:
                request.POST['amount'] = \
                    request.POST['amount'][1:] \
                    if request.POST['amount'][0] == '-' \
                    else '-' + request.POST['amount']
                request.POST['amount_acc_cur'] = \
                    request.POST['amount_acc_cur'][1:] \
                    if request.POST['amount_acc_cur'][0] == '-' \
                    else '-' + request.POST['amount_acc_cur']
                if request.POST['currency'] == str(t.account.currency.id):
                    request.POST['amount'] = request.POST['amount_acc_cur']
        request.POST._mutable = old

        form = TransactionEditForm(budget_id=t.budget.pk, is_linked_movement=is_linked_movement, instance=t,
                                   data=request.POST)
        if is_time_transaction_error:
            form.add_error('form_time_transaction', valid_datetime_formats)

    else:

        form = TransactionEditForm(budget_id=t.budget.pk, is_linked_movement=is_linked_movement, instance=t,
                                   initial={'form_time_transaction':
                                            t.time_transaction + timedelta(hours=float(t.time_zone)),
                                            },
                                   )

    return render(request, 'main/transaction_edit.html',
                  get_u_context(request,
                                {'title': 'Изменение операции',
                                 'form': form,
                                 'account_selected': t.account.id,
                                 'different_currency': t.account.currency.id != t.currency.id,
                                 'non_move_transaction': t.type in ['CRE', 'DEB'],
                                 'account_currency': t.account.currency.iso_code,
                                 'account_currency_id': t.account.currency.pk,
                                 'is_account_not_cash': t.account.type not in ALL_CASH_ACCOUNT,
                                 'transaction_name': transaction_name,
                                 'work_menu': True,
                                 'selected_menu': 'account_transactions',
                                 'return_url': return_url}))


class DeleteTransaction(LoginRequiredMixin, DataMixin, DeleteView):
    """
    Функция удаления операции
    """
    model = Transaction
    template_name = 'main/transaction_delete.html'
    pk_url_kwarg = 'transaction_id'
    login_url = reverse_lazy('login')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        t = get_object_or_404(Transaction, pk=self.kwargs['transaction_id'])
        return_url = self.kwargs['return_url']
        if return_url[0:1] != '/':
            return_url = '/' + return_url
        c_def = self.get_user_context(title='Удаление операции',
                                      account_selected=t.account.id,
                                      transaction_name=str(t),
                                      work_menu=True,
                                      selected_menu='account_transactions',
                                      return_url=return_url)
        return dict(list(context.items()) + list(c_def.items()))

    def get_success_url(self):
        return_url = self.kwargs['return_url']
        if return_url[0:1] != '/':
            return_url = '/' + return_url
        return return_url

    def dispatch(self, request, *args, **kwargs):
        t = get_object_or_404(Transaction, pk=self.kwargs['transaction_id'])
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if t.budget != request.user.profile.budget:
                return self.handle_no_permission()
        return super(DeleteTransaction, self).dispatch(request, *args, **kwargs)


@login_required
def manage_transaction_category(request, transaction_id, return_url):
    """
    Функция изменения списка категорий операции
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')

    if return_url[0:1] != '/':
        return_url = '/' + return_url

    t = get_object_or_404(Transaction, pk=transaction_id)

    if t.type in ['DEB', 'MO-']:
        transaction_amount = -t.amount_acc_cur
    else:
        transaction_amount = t.amount_acc_cur

    if t.budget != request.user.profile.budget:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")

    if request.method == 'POST':

        old = request.POST._mutable
        request.POST._mutable = True
        for idx in range(15):
            if t.type in ['DEB', 'MO-']:
                s_idx = 'transaction_categories-' + str(idx) + '-amount_acc_cur'
                if request.POST[s_idx] != '0.0':
                    request.POST[s_idx] = \
                        request.POST[s_idx][1:] \
                        if request.POST[s_idx][0] == '-' \
                        else '-' + request.POST[s_idx]
            category_idx = 'transaction_categories-' + str(idx) + '-category'
            category_form_idx = 'transaction_categories-' + str(idx) + '-category_form'
            budget_object_idx = 'transaction_categories-' + str(idx) + '-budget_object'
            request.POST[category_idx] = \
                Category.get_category_with_object(t.budget,
                                                  request.POST[category_form_idx],
                                                  request.POST[budget_object_idx],
                                                  request.user)
        request.POST._mutable = old

        formset = TransactionCategoryFormset(request.POST, instance=t, form_kwargs={'parent': t})

        if formset.is_valid():
            try:
                with transaction.atomic():
                    formset.save()

                    # 1. Получим набор категорий по операции
                    transaction_categories = TransactionCategory.objects.filter(transaction_id=t.pk)

                    # 2 Кейс с отсутствием категории не обрабатываем, ибо такое возможно при создании - здесь
                    #   категория создастся следом
                    pass

                    # 3. Если у операции только одна категория, то поменяем суммы в базовых валютах у категории
                    if len(transaction_categories) == 1:
                        transaction_category = transaction_categories[0]
                        is_transaction_category_update = False
                        if transaction_category.amount_base_cur_1 != ftod(t.amount_base_cur_1, 2):
                            transaction_category.amount_base_cur_1 = ftod(t.amount_base_cur_1, 2)
                            is_transaction_category_update = True
                        if transaction_category.amount_base_cur_2 != ftod(t.amount_base_cur_2, 2):
                            transaction_category.amount_base_cur_2 = ftod(t.amount_base_cur_2, 2)
                            is_transaction_category_update = True
                        if is_transaction_category_update:
                            transaction_category.save()

                    # 4. Если у операции несколько категорий, то творим магию - обновляем суммы в базовых валютах у
                    #    категорий в соответствие долям распределения основных сумм категорий операции
                    if len(transaction_categories) > 1:
                        # 4.1. Посчитаем текущую сумму основных сумм категорий операции
                        categories_sum = ftod(0.00, 2)
                        for transaction_category in transaction_categories:
                            categories_sum = categories_sum + ftod(transaction_category.amount_acc_cur, 2)

                        # 4.2. Обновим суммы каждой категории
                        new_sum_amount_base_cur_1 = ftod(0.00, 2)
                        new_sum_amount_base_cur_2 = ftod(0.00, 2)

                        for i, transaction_category in enumerate(transaction_categories):
                            is_transaction_category_update = False

                            if i < len(transaction_categories) - 1:
                                # Для всех, кроме последней
                                proportion = transaction_category.amount_acc_cur / categories_sum
                                if transaction_category.amount_base_cur_1 != ftod(t.amount_base_cur_1 * proportion, 2):
                                    transaction_category.amount_base_cur_1 = ftod(t.amount_base_cur_1 * proportion, 2)
                                    is_transaction_category_update = True
                                new_sum_amount_base_cur_1 = \
                                    new_sum_amount_base_cur_1 + \
                                    transaction_category.amount_base_cur_1
                                if transaction_category.amount_base_cur_2 != ftod(t.amount_base_cur_2 * proportion, 2):
                                    transaction_category.amount_base_cur_2 = ftod(t.amount_base_cur_2 * proportion, 2)
                                    is_transaction_category_update = True
                                new_sum_amount_base_cur_2 = \
                                    new_sum_amount_base_cur_2 + \
                                    transaction_category.amount_base_cur_2
                            else:
                                # для последней берем точный остаток от суммы операции за минусом суммы предыдущих
                                # категорий, чтобы избежать копеек разницы из-за округления
                                if transaction_category.amount_base_cur_1 != ftod(t.amount_base_cur_1 -
                                                                                  new_sum_amount_base_cur_1, 2):
                                    transaction_category.amount_base_cur_1 = ftod(t.amount_base_cur_1 -
                                                                                  new_sum_amount_base_cur_1, 2)
                                    is_transaction_category_update = True
                                if transaction_category.amount_base_cur_2 != ftod(t.amount_base_cur_2 -
                                                                                  new_sum_amount_base_cur_2, 2):
                                    transaction_category.amount_base_cur_2 = ftod(t.amount_base_cur_2 -
                                                                                  new_sum_amount_base_cur_2, 2)
                                    is_transaction_category_update = True

                            if is_transaction_category_update:
                                transaction_category.save()

                    return redirect(return_url)
            except Exception as e:
                print('Что-то с сохранением категорий операции пошло не так: ' + str(e))

        if t.type in ['DEB', 'MO-']:
            old = request.POST._mutable
            request.POST._mutable = True
            for idx in range(15):
                s_idx = 'transaction_categories-' + str(idx) + '-amount_acc_cur'
                if request.POST[s_idx] != '0.0':
                    request.POST[s_idx] = \
                        request.POST[s_idx][1:] \
                        if request.POST[s_idx][0] == '-' \
                        else '-' + request.POST[s_idx]
            request.POST._mutable = old
            formset = TransactionCategoryFormset(request.POST, instance=t, form_kwargs={'parent': t})

    else:
        formset = TransactionCategoryFormset(instance=t, form_kwargs={'parent': t})

    return render(request, 'main/transaction_category_edit.html',
                  get_u_context(request,
                                {'title': 'Распределение суммы операции по категориям',
                                 'parent': t,
                                 'transaction_category_formset': formset,
                                 'transaction_id': transaction_id,
                                 'transaction_type': t.type,
                                 'account_currency': t.account.currency.iso_code,
                                 'transaction_name': str(t),
                                 'transaction_amount': transaction_amount,
                                 'work_menu': True,
                                 'account_selected': t.account.id,
                                 'selected_menu': 'account_transactions',
                                 'return_url': return_url
                                 }))


@login_required
def set_join_between_transactions(request, transaction_id, return_url):
    """
    Функция установки связи между операциями перемещения
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')

    changed_transaction = Transaction.objects.get(pk=transaction_id)
    if changed_transaction.budget != request.user.profile.budget:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")

    if return_url[0:1] != '/':
        return_url = '/' + return_url
    if request.method == 'POST':
        pass
    elif changed_transaction.type in ('MO+', 'MO-'):
        search_type = 'MO-' if changed_transaction.type == 'MO+' else 'MO+'
        search_start_time = changed_transaction.time_transaction - DEFAULT_TIME_DELTA \
            if changed_transaction.type == 'MO+' \
            else changed_transaction.time_transaction
        search_end_time = changed_transaction.time_transaction \
            if changed_transaction.type == 'MO+' \
            else changed_transaction.time_transaction + DEFAULT_TIME_DELTA
        suitable_transactions = Transaction.objects.filter(budget_id=changed_transaction.budget.id,
                                                           time_transaction__gte=search_start_time,
                                                           time_transaction__lte=search_end_time,
                                                           type=search_type,
                                                           amount=-changed_transaction.amount,
                                                           currency_id=changed_transaction.currency.id,
                                                           sender__isnull=True,
                                                           receiver__isnull=True
                                                           ).exclude(account_id=changed_transaction.account.id)

        if len(suitable_transactions) == 1:
            try:
                with transaction.atomic():
                    if changed_transaction.type == 'MO+':
                        changed_transaction.sender = suitable_transactions[0]
                        changed_transaction.user_update = request.user
                        changed_transaction.save()
                    elif changed_transaction.type == 'MO-':
                        suitable_transactions[0].sender = changed_transaction
                        changed_transaction.user_update = request.user
                        suitable_transactions[0].save()
            except Exception as e:
                print('Что-то пошло не так с установлением связи между операциями - ' + str(e))
            return redirect(return_url)
        else:
            if changed_transaction.type == 'MO+':
                return custom_redirect('account_transactions_for_join', transaction_id, return_url,
                                       time_transaction_min=search_start_time.strftime(
                                           formats.get_format("DATETIME_INPUT_FORMATS",
                                                              lang=translation.get_language())[0]
                                       ),
                                       time_transaction_max=search_end_time.strftime(
                                           formats.get_format("DATETIME_INPUT_FORMATS",
                                                              lang=translation.get_language())[0]
                                       ),
                                       amount_exp_min=changed_transaction.amount,
                                       amount_exp_max=changed_transaction.amount,
                                       currency=changed_transaction.currency.iso_code)
            else:
                return custom_redirect('account_transactions_for_join', transaction_id, return_url,
                                       time_transaction_min=search_start_time.strftime(
                                           formats.get_format("DATETIME_INPUT_FORMATS",
                                                              lang=translation.get_language())[0]
                                       ),
                                       time_transaction_max=search_end_time.strftime(
                                           formats.get_format("DATETIME_INPUT_FORMATS",
                                                              lang=translation.get_language())[0]
                                       ),
                                       amount_inc_min=-changed_transaction.amount,
                                       amount_inc_max=-changed_transaction.amount,
                                       currency=changed_transaction.currency.iso_code)
    return redirect(return_url)


class AccountTransactionsForJoin(LoginRequiredMixin, DataMixin, ListView):
    """
    Класс списка операций перемещения для выбора для установки связи между ними
    """
    model = Transaction
    template_name = 'main/account_transactions_for_join.html'
    context_object_name = 'transactions'
    allow_empty = True
    account_transaction_filter = None
    success_url = reverse_lazy('home')

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(AccountTransactionsForJoin, self).get_context_data(**kwargs)
        t = get_object_or_404(Transaction, pk=self.kwargs['transaction_id'])
        search_start_time = t.time_transaction - DEFAULT_TIME_DELTA \
            if t.type == 'MO+' \
            else t.time_transaction
        search_end_time = t.time_transaction \
            if t.type == 'MO+' \
            else t.time_transaction + DEFAULT_TIME_DELTA
        return_url = self.kwargs['return_url']
        if return_url[0:1] != '/':
            return_url = '/' + return_url
        c_def = self.get_user_context(title='Выбор перемещения для связи',
                                      filter=self.account_transaction_filter,
                                      account_selected=t.account_id,
                                      transaction_for_join=t,
                                      transaction_for_join_type=t.type,
                                      transaction_for_join_time_transaction=t.time_transaction.strftime(
                                          formats.get_format("DATETIME_INPUT_FORMATS",
                                                             lang=translation.get_language())[0]
                                      ),
                                      transaction_for_join_start_time=search_start_time,
                                      transaction_for_join_end_time=search_end_time,
                                      transaction_for_join_amount=t.amount,
                                      transaction_for_join_currency_iso_code=t.currency.iso_code,
                                      transaction_for_join_currency_id=t.currency.id,
                                      return_url=return_url,
                                      work_menu=True,
                                      selected_menu='account_transactions')
        return dict(list(context.items()) + list(c_def.items()))

    def dispatch(self, request, *args, **kwargs):
        t = get_object_or_404(Transaction, pk=self.kwargs['transaction_id'])
        return_url = self.kwargs['return_url']
        if return_url[0:1] != '/':
            return_url = '/' + return_url
        self.success_url = return_url
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if t.budget != request.user.profile.budget:
                return self.handle_no_permission()
        if t.type not in ['MO-', 'MO+']:
            return redirect('home')

        search_type = 'MO-' if t.type == 'MO+' else 'MO+'
        self.account_transaction_filter = \
            AccountTransactionsFilterForJoin(
                request.GET, request=request,
                queryset=(Transaction.objects
                          .annotate(a_name=Concat(F('account__name'),
                                                  Value(' ('),
                                                  F('account__currency__iso_code'),
                                                  Value(')'),
                                                  output_field=models.CharField()))
                          .filter(budget_id=t.budget.id,
                                  type=search_type,
                                  sender__isnull=True,
                                  receiver__isnull=True
                                  )
                          .exclude(account_id=t.account.id)
                          .order_by('-time_transaction')
                          .select_related('budget', 'account', 'currency', 'sender')
                          )
            )
        self.queryset = self.account_transaction_filter.qs
        return super(AccountTransactionsForJoin, self).dispatch(request, *args, **kwargs)


@login_required
def join_confirmation_between_transactions(request, sender_id, receiver_id, return_url):
    """
    Функция подтверждения выбора операций перемещения для установки связи между ними
    """

    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')

    sender_transaction = get_object_or_404(Transaction, pk=sender_id)
    receiver_transaction = get_object_or_404(Transaction, pk=receiver_id)
    if sender_transaction.budget != request.user.profile.budget:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")
    if receiver_transaction.budget != request.user.profile.budget:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")
    if return_url[0:1] != '/':
        return_url = '/' + return_url
    if sender_transaction.type != 'MO-':
        return redirect(return_url)
    if receiver_transaction.type != 'MO+':
        return redirect(return_url)
    if hasattr(sender_transaction, 'receiver') and sender_transaction.receiver is not None:
        return redirect(return_url)
    if receiver_transaction.sender is not None:
        return redirect(return_url)

    if request.method == 'GET':
        is_time_transaction_valid = \
            sender_transaction.time_transaction <= \
            receiver_transaction.time_transaction <= \
            sender_transaction.time_transaction + DEFAULT_TIME_DELTA
        is_amount_valid = receiver_transaction.amount == -sender_transaction.amount_acc_cur
        is_currency_valid = receiver_transaction.currency == sender_transaction.account.currency

        if is_time_transaction_valid and is_amount_valid and is_currency_valid:
            try:
                with transaction.atomic():
                    receiver_transaction.sender = sender_transaction
                    receiver_transaction.user_update = request.user
                    receiver_transaction.save()
            except Exception as e:
                print('Что-то пошло не так с установлением связи между операциями - ' + str(e))
            return redirect(return_url)

        if is_time_transaction_valid:
            difference_in_time = ''
            old_time = receiver_transaction.time_transaction
            new_time = receiver_transaction.time_transaction
        else:
            difference_in_time = sender_transaction.time_transaction - receiver_transaction.time_transaction
            old_time = receiver_transaction.time_transaction
            new_time = sender_transaction.time_transaction
            if difference_in_time.days == 0:
                difference_in_time = str(difference_in_time)
            elif abs(difference_in_time.days) % 10 == 1:
                difference_in_time = str(difference_in_time).replace('days', 'день').replace('day', 'день')
            elif 0 < abs(difference_in_time.days) % 10 <= 4:
                difference_in_time = str(difference_in_time).replace('days', 'дня')
            else:
                difference_in_time = str(difference_in_time).replace('days', 'дней')
            difference_in_time = 'Разница во времени составила: ' + difference_in_time

        transaction_currency = sender_transaction.currency
        account_currency = receiver_transaction.account.currency
        if is_currency_valid:
            old_currency = receiver_transaction.currency
            new_currency = receiver_transaction.currency
            difference_in_currency = ''
            if is_amount_valid:
                old_amount = receiver_transaction.amount
                new_amount = receiver_transaction.amount
                difference_in_amount = ''
                old_amount_acc_cur = receiver_transaction.amount_acc_cur
                new_amount_acc_cur = receiver_transaction.amount_acc_cur
                difference_in_amount_acc_cur = ''
            else:
                old_amount = receiver_transaction.amount
                new_amount = -sender_transaction.amount_acc_cur
                difference_in_amount = 'Разница в сумме операции составила: ' + \
                                       number_format(new_amount - old_amount,
                                                     decimal_pos=2, use_l10n=True, force_grouping=True) + ' ' + \
                                       new_currency.iso_code
                if transaction_currency == account_currency:
                    old_amount_acc_cur = receiver_transaction.amount_acc_cur
                    new_amount_acc_cur = -sender_transaction.amount_acc_cur
                    difference_in_amount_acc_cur = \
                        'Разница в сумме операции в валюте счета составила: ' + \
                        number_format(new_amount_acc_cur - old_amount_acc_cur,
                                      decimal_pos=2, use_l10n=True, force_grouping=True) + ' ' + \
                        new_currency.iso_code
                else:
                    old_amount_acc_cur = receiver_transaction.amount_acc_cur
                    new_amount_acc_cur = receiver_transaction.amount_acc_cur
                    if new_amount_acc_cur > new_amount:
                        difference_in_amount_acc_cur = \
                            'Изменился курс операции: ' + \
                            number_format(old_amount_acc_cur / old_amount,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            receiver_transaction.account.currency.iso_code + '/' + \
                            old_currency.iso_code + ' -> ' + \
                            number_format(new_amount_acc_cur / new_amount,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            account_currency.iso_code + '/' + transaction_currency.iso_code
                    else:
                        difference_in_amount_acc_cur = \
                            'Изменился курс операции: ' + \
                            number_format(old_amount / old_amount_acc_cur,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            old_currency.iso_code + '/' + \
                            receiver_transaction.account.currency.iso_code + ' -> ' + \
                            number_format(new_amount / new_amount_acc_cur,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            transaction_currency.iso_code + '/' + account_currency.iso_code
        else:
            old_currency = receiver_transaction.currency
            new_currency = sender_transaction.account.currency
            difference_in_currency = 'Валюта операции изменилась: ' + old_currency.iso_code + \
                                     ' -> ' + new_currency.iso_code
            if is_amount_valid:
                old_amount = receiver_transaction.amount
                new_amount = receiver_transaction.amount
                difference_in_amount = ''
                if transaction_currency == account_currency:
                    old_amount_acc_cur = receiver_transaction.amount_acc_cur
                    new_amount_acc_cur = -sender_transaction.amount
                    difference_in_amount_acc_cur = \
                        'Разница в сумме операции в валюте счета составила: ' + \
                        number_format(new_amount_acc_cur - old_amount_acc_cur,
                                      decimal_pos=2, use_l10n=True, force_grouping=True) + ' ' + \
                        new_currency.iso_code
                else:
                    old_amount_acc_cur = receiver_transaction.amount_acc_cur
                    new_amount_acc_cur = receiver_transaction.amount_acc_cur
                    if new_amount_acc_cur > new_amount:
                        difference_in_amount_acc_cur = \
                            'Изменился курс операции: ' + \
                            number_format(old_amount_acc_cur / old_amount,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            receiver_transaction.account.currency.iso_code + '/' + \
                            old_currency.iso_code + ' -> ' + \
                            number_format(new_amount_acc_cur / new_amount,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            account_currency.iso_code + '/' + transaction_currency.iso_code
                    else:
                        difference_in_amount_acc_cur = \
                            'Изменился курс операции: ' + \
                            number_format(old_amount / old_amount_acc_cur,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            old_currency.iso_code + '/' + \
                            receiver_transaction.account.currency.iso_code + ' -> ' + \
                            number_format(new_amount / new_amount_acc_cur,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            transaction_currency.iso_code + '/' + account_currency.iso_code
            else:
                old_amount = receiver_transaction.amount
                new_amount = -sender_transaction.amount_acc_cur
                difference_in_amount = 'Сумма операции изменилась: ' + \
                                       number_format(old_amount,
                                                     decimal_pos=2, use_l10n=True, force_grouping=True) + ' ' + \
                                       old_currency.iso_code + ' -> ' + \
                                       number_format(new_amount,
                                                     decimal_pos=2, use_l10n=True, force_grouping=True) + ' ' + \
                                       new_currency.iso_code
                if transaction_currency == account_currency:
                    old_amount_acc_cur = receiver_transaction.amount_acc_cur
                    new_amount_acc_cur = -sender_transaction.amount_acc_cur
                    difference_in_amount_acc_cur = \
                        'Разница в сумме операции в валюте счета составила: ' + \
                        number_format(new_amount_acc_cur - old_amount_acc_cur,
                                      decimal_pos=2, use_l10n=True, force_grouping=True) + ' ' + \
                        new_currency.iso_code
                else:
                    old_amount_acc_cur = receiver_transaction.amount_acc_cur
                    new_amount_acc_cur = receiver_transaction.amount_acc_cur
                    if new_amount_acc_cur > new_amount:
                        difference_in_amount_acc_cur = \
                            'Изменился курс операции: ' + \
                            number_format(old_amount_acc_cur / old_amount,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            receiver_transaction.account.currency.iso_code + '/' + \
                            old_currency.iso_code + ' -> ' + \
                            number_format(new_amount_acc_cur / new_amount,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            account_currency.iso_code + '/' + transaction_currency.iso_code
                    else:
                        difference_in_amount_acc_cur = \
                            'Изменился курс операции: ' + \
                            number_format(old_amount / old_amount_acc_cur,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            old_currency.iso_code + '/' + \
                            receiver_transaction.account.currency.iso_code + ' -> ' + \
                            number_format(new_amount / new_amount_acc_cur,
                                          decimal_pos=5, use_l10n=True, force_grouping=True) + ' ' + \
                            transaction_currency.iso_code + '/' + account_currency.iso_code

        form = JoinConfirmationForm(initial={'old_time': old_time,
                                             'new_time': new_time,
                                             'old_currency': old_currency.iso_code,
                                             'new_currency': new_currency.iso_code,
                                             'new_currency_id': new_currency.id,
                                             'old_amount': old_amount,
                                             'new_amount': new_amount,
                                             'old_amount_acc_cur': old_amount_acc_cur,
                                             'new_amount_acc_cur': new_amount_acc_cur,
                                             },
                                    )

        return render(request, 'main/account_transactions_join_confirmation.html',
                      get_u_context(request,
                                    {'title': 'Подтверждение создания связи между перемещениями',
                                     'form': form,
                                     'sender_transaction': sender_transaction,
                                     'receiver_transaction': receiver_transaction,
                                     'difference_in_time': difference_in_time,
                                     'difference_in_currency': difference_in_currency,
                                     'difference_in_amount': difference_in_amount,
                                     'difference_in_amount_acc_cur': difference_in_amount_acc_cur,
                                     'work_menu': True,
                                     'selected_menu': 'account_transactions',
                                     'account_selected': sender_transaction.account.id,
                                     'return_url': return_url}))

    elif request.method == 'POST':
        try:
            with transaction.atomic():
                if receiver_transaction.time_transaction < \
                        sender_transaction.time_transaction or \
                        sender_transaction.time_transaction + DEFAULT_TIME_DELTA < \
                        receiver_transaction.time_transaction:
                    receiver_transaction.time_transaction = sender_transaction.time_transaction
                receiver_transaction.currency = sender_transaction.account.currency
                receiver_transaction.amount = -sender_transaction.amount_acc_cur
                if receiver_transaction.currency == receiver_transaction.account.currency:
                    receiver_transaction.amount_acc_cur = receiver_transaction.amount
                receiver_transaction.sender = sender_transaction
                receiver_transaction.user_update = request.user
                receiver_transaction.save()
        except Exception as e:
            print('Что-то пошло не так с установлением связи между операциями - ' + str(e))
        return redirect(return_url)

    return redirect(return_url)


@login_required
def delete_join_between_transactions(request, transaction_id, return_url):
    """
    Функция удаления связи между операциями перемещения
    """

    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    changed_transaction = Transaction.objects.get(pk=transaction_id)
    if changed_transaction.budget != request.user.profile.budget:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")

    if return_url[0:1] != '/':
        return_url = '/' + return_url
    try:
        with transaction.atomic():
            if changed_transaction.type == 'MO+':
                changed_transaction.sender = None
                changed_transaction.user_update = request.user
                changed_transaction.save()
            elif changed_transaction.type == 'MO-':
                changed_transaction = changed_transaction.receiver
                changed_transaction.user_update = request.user
                changed_transaction.sender = None
                changed_transaction.save()
    except Exception as e:
        print('Что-то пошло не так с удалением связи между операциями - ' + str(e))
    return redirect(return_url)


@login_required
def balances_recalculation(request, budget_id, return_url):
    """
    Процедура пересчета остатков

    В данной процедуре производится расчет атрибутов операций, необходимые для расчета бюджета:
    - остаток по счету в валюте счета;
    - остатки по счету в базовой и дополнительной валютах бюджета;
    - суммы операции в базовой и дополнительной валютах бюджета.
    Изменение сумм операции в базовой и дополнительной валютах бюджета повлечет за собой через
    метод Transaction.save() изменение сумм категорий операции, которое в свою очередь через
    метод TransactionCategory.save() изменит значения бюджетных регистров BudgetRegister - таким
    образом будут обновлены данные по бюджету.

    Алгоритм такой:
    - отбираются счета, по операциям которых нужно произвести пересчет, и определяется дата,
    с которой нужно производить пересчет;
    - проверяется наличие операций курсовой разницы в заданном интервале (в каждом месяце
    по каждому счету должны быть операции положительной и отрицательной курсовой разницы,
    они имеют дату-время - последние две микросекунды последнего дня месяца), при отсутствии
    в каком-то месяце этих операций они добавляются;
    - операции выстраиваются по времени создания (необходимо для расчета остатков),
    и производится пересчет атрибутов.
    """

    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    if budget_id != request.user.profile.budget.pk:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")

    if return_url[0:1] != '/':
        return_url = '/' + return_url

    if request.method != 'GET':
        return redirect(return_url)

    # Отбираются операции перемещения без связи
    unlinked_movement_transactions = \
        Transaction.objects.filter(budget_id=budget_id, type='MO+', sender_id__isnull=True).order_by('time_transaction')

    # При наличии несвязанных операций перемещения, процедура завершается, пользователю выдается список этих операций
    if len(unlinked_movement_transactions) > 0:
        return redirect(account_transactions_without_join, budget_id, return_url)

    is_error = False

    b = Budget.objects.get(pk=budget_id)
    budget_base_currency_1 = b.base_currency_1_id
    budget_base_currency_2 = b.base_currency_2_id

    # Формируем массив счетов для пересчета остатков
    try:
        with transaction.atomic():
            first_transaction_time = None
            first_transactions = \
                Transaction.objects.filter(budget_id=budget_id).order_by('time_transaction')[:1]
            if len(first_transactions) > 0:
                first_transaction_time = datetime(first_transactions[0].time_transaction.year, 1, 1,
                                                  0, 0, 0, 0, timezone.utc)
                # Сначала проверим счета с начальным остатком на наличие ранних операций курсовой разницы

                # Для счетов с ненулевым начальным остатком, у которых операции курсовой разницы начинаются позже первой
                # операции в бюджете (это возникнет, когда добавили более раннюю операцию по любому из счетов) снесем
                # флаг валидности и дату валидности остатков переместим на первое января года даты первой операции в
                # бюджете. Это для создания операций курсовой разницы вначале, ибо бюджет должен учитывать курсовую
                # разницу на начальным остаткам, начиная с начала года первой операции по бюджету
                accounts_with_initial_balance = \
                    Account.objects.filter(budget_id=budget_id).exclude(initial_balance=ftod(0.00, 2))
                for account_with_initial_balance in accounts_with_initial_balance:
                    first_transactions = \
                        Transaction.objects.filter(budget_id=budget_id,
                                                   account_id=account_with_initial_balance.pk
                                                   ).order_by('time_transaction')[:1]
                    if len(first_transactions) > 0:
                        first_time = datetime(first_transactions[0].time_transaction.year,
                                              first_transactions[0].time_transaction.month,
                                              1, 0, 0, 0, 0, timezone.utc)
                    else:
                        first_time = datetime(datetime.utcnow().year, datetime.utcnow().month, 1,
                                              0, 0, 0, 0, timezone.utc)

                    if first_time > first_transaction_time:
                        # Выявили счет, у которого ненулевой начальный остаток и дата первой операции позже первой
                        # операции в бюджете
                        account_with_initial_balance.is_balances_valid = False
                        account_with_initial_balance.balances_valid_until = first_transaction_time
                        account_with_initial_balance.save()

            # Сформируем стартовый массив счетов для пересчета по наличию отключенного флага валидности
            accounts_with_invalid_balances = \
                [account for account in Account.objects.filter(budget_id=budget_id, is_balances_valid=False)]

            # Пробежимся по операциям перемещения расход у счетов из выше сформированного массива, определим по ним
            # счет-приемник, и, если у этого счета установлен флаг валидности или дата валидности позже даты
            # перемещения, то снесем флаг валидности, подвинем дату валидности и добавим этот счет
            # в массив для пересчета
            idx = 0
            while idx < len(accounts_with_invalid_balances):
                account_with_invalid_balances = accounts_with_invalid_balances[idx]
                outbound_movements = \
                    Transaction.objects.filter(budget_id=budget_id,
                                               account_id=account_with_invalid_balances.pk,
                                               time_transaction__gte=account_with_invalid_balances.balances_valid_until,
                                               type='MO-'
                                               ).order_by('time_transaction')
                for outbound_movement in outbound_movements:
                    try:
                        incoming_movement = outbound_movement.receiver
                    except Exception as e:
                        incoming_movement = None
                    if incoming_movement:
                        is_account_update = False
                        if incoming_movement.account.is_balances_valid:
                            # Снесем флаг валидности у счета-приемника
                            incoming_movement.account.is_balances_valid = False
                            is_account_update = True
                        if incoming_movement.account.balances_valid_until > incoming_movement.time_transaction:
                            # Установим новую дату валидности у счета-приемника
                            incoming_movement.account.balances_valid_until = incoming_movement.time_transaction
                            is_account_update = True
                        if is_account_update:
                            # Сохраним счет-приемник
                            incoming_movement.account.save()
                            if incoming_movement.account not in accounts_with_invalid_balances[idx + 1:]:
                                # Добавим в результирующий массив счет-приемник
                                accounts_with_invalid_balances.append(incoming_movement.account)
                idx = idx + 1

    except Exception as e:
        is_error = True

    try:
        with transaction.atomic():
            # Проверим наличие Операций курсовой разницы для каждого счета из сформированного массива счетов

            # Вычислим конечную дату интервала проверки (она для всех счетов единая)
            last_transaction_time = min(MAX_TRANSACTION_DATETIME,
                                        datetime(datetime.utcnow().year,
                                                 datetime.utcnow().month,
                                                 last_day_of_month(datetime.utcnow()).day,
                                                 23, 59, 59, 999999, timezone.utc))
            for account_with_invalid_balances in accounts_with_invalid_balances:
                # Вычислим начальную дату интервала проверки для счета
                if first_transaction_time:
                    time_new_transaction = \
                        max(MIN_TRANSACTION_DATETIME,
                            datetime(first_transaction_time.year,
                                     first_transaction_time.month,
                                     last_day_of_month(first_transaction_time).day,
                                     23, 59, 59, 999999, timezone.utc))
                else:
                    time_new_transaction = last_transaction_time

                # Отберем операции курсовой разницы (возьмем ED-)
                exchange_difference_transactions = \
                    Transaction.objects.filter(budget_id=account_with_invalid_balances.budget_id,
                                               account_id=account_with_invalid_balances.pk,
                                               type='ED-',
                                               ).order_by('time_transaction')
                for t in exchange_difference_transactions:
                    # Заводим отсутствующие операции курсовой разницы в интервале проверки
                    while time_new_transaction < t.time_transaction:
                        # Сначала операцию положительной курсовой разницы
                        new_ped_transaction = Transaction()
                        new_ped_transaction.budget = account_with_invalid_balances.budget
                        new_ped_transaction.account = account_with_invalid_balances
                        new_ped_transaction.type = 'ED+'
                        new_ped_transaction.time_transaction = time_new_transaction - timedelta(microseconds=1)
                        new_ped_transaction.currency = account_with_invalid_balances.currency
                        new_ped_transaction.budget_year = time_new_transaction.year
                        new_ped_transaction.budget_month = time_new_transaction.month
                        new_ped_transaction.user_create = request.user
                        new_ped_transaction.user_update = request.user
                        new_ped_transaction.save()

                        new_ped_transaction_category = TransactionCategory()
                        new_ped_transaction_category.transaction = new_ped_transaction
                        new_ped_transaction_category.category_id = POSITIVE_EXCHANGE_DIFFERENCE
                        new_ped_transaction_category.save()

                        # Затем операцию отрицательной курсовой разницы
                        new_ned_transaction = Transaction()
                        new_ned_transaction.budget = account_with_invalid_balances.budget
                        new_ned_transaction.account = account_with_invalid_balances
                        new_ned_transaction.type = 'ED-'
                        new_ned_transaction.time_transaction = time_new_transaction
                        new_ned_transaction.currency = account_with_invalid_balances.currency
                        new_ned_transaction.budget_year = time_new_transaction.year
                        new_ned_transaction.budget_month = time_new_transaction.month
                        new_ned_transaction.user_create = request.user
                        new_ned_transaction.user_update = request.user
                        new_ned_transaction.save()

                        new_ned_transaction_category = TransactionCategory()
                        new_ned_transaction_category.transaction = new_ned_transaction
                        new_ned_transaction_category.category_id = NEGATIVE_EXCHANGE_DIFFERENCE
                        new_ned_transaction_category.save()

                        # Вычисляем дату операции курсовой разницы следующего периода
                        time_new_transaction = time_new_transaction + timedelta(microseconds=10)
                        time_new_transaction = datetime(time_new_transaction.year,
                                                        time_new_transaction.month,
                                                        last_day_of_month(time_new_transaction).day,
                                                        23, 59, 59, 999999, timezone.utc)
                    if time_new_transaction == t.time_transaction:
                        time_new_transaction = time_new_transaction + timedelta(microseconds=10)
                        time_new_transaction = datetime(time_new_transaction.year,
                                                        time_new_transaction.month,
                                                        last_day_of_month(time_new_transaction).day,
                                                        23, 59, 59, 999999, timezone.utc)

                # После цикла по существующим операциям курсовой разницы пройдемся еще
                # по следующим месяцам до текущей даты, и также создадим в этих месяцах
                # операции курсовой разницы
                while time_new_transaction <= last_transaction_time:
                    # Сначала операцию положительной курсовой разницы
                    new_ped_transaction = Transaction()
                    new_ped_transaction.budget = account_with_invalid_balances.budget
                    new_ped_transaction.account = account_with_invalid_balances
                    new_ped_transaction.type = 'ED+'
                    new_ped_transaction.time_transaction = time_new_transaction - timedelta(microseconds=1)
                    new_ped_transaction.currency = account_with_invalid_balances.currency
                    new_ped_transaction.budget_year = time_new_transaction.year
                    new_ped_transaction.budget_month = time_new_transaction.month
                    new_ped_transaction.user_create = request.user
                    new_ped_transaction.user_update = request.user
                    new_ped_transaction.save()

                    new_ped_transaction_category = TransactionCategory()
                    new_ped_transaction_category.transaction = new_ped_transaction
                    new_ped_transaction_category.category_id = POSITIVE_EXCHANGE_DIFFERENCE
                    new_ped_transaction_category.save()

                    # Затем операцию отрицательной курсовой разницы
                    new_ned_transaction = Transaction()
                    new_ned_transaction.budget = account_with_invalid_balances.budget
                    new_ned_transaction.account = account_with_invalid_balances
                    new_ned_transaction.type = 'ED-'
                    new_ned_transaction.time_transaction = time_new_transaction
                    new_ned_transaction.currency = account_with_invalid_balances.currency
                    new_ned_transaction.budget_year = time_new_transaction.year
                    new_ned_transaction.budget_month = time_new_transaction.month
                    new_ned_transaction.user_create = request.user
                    new_ned_transaction.user_update = request.user
                    new_ned_transaction.save()

                    new_ned_transaction_category = TransactionCategory()
                    new_ned_transaction_category.transaction = new_ned_transaction
                    new_ned_transaction_category.category_id = NEGATIVE_EXCHANGE_DIFFERENCE
                    new_ned_transaction_category.save()

                    # Вычисляем дату операции курсовой разницы следующего периода
                    time_new_transaction = time_new_transaction + timedelta(microseconds=10)
                    time_new_transaction = datetime(time_new_transaction.year,
                                                    time_new_transaction.month,
                                                    last_day_of_month(time_new_transaction).day,
                                                    23, 59, 59, 999999, timezone.utc)

    except Exception as e:
        is_error = True

    # Если были ошибки, то прерываем процедуру
    if is_error:
        return redirect(return_url)

    # Расширим массив счетов дополнительными атрибутами
    # Каждый элемент это словарь:
    # - счет;
    # - список операций для пересчета;
    # - текущий номер операции;
    # - текущая операция;
    # - предыдущая операция.
    accounts_with_invalid_balances = \
        [{"account": account, "transactions": None, "idx": 0, "transaction": None, "previous_transaction": None}
         for account in accounts_with_invalid_balances]

    # Отбираем операции по счетам из массива и записываем их в соответствующий атрибут массива
    transactions_count = 0
    for account_with_invalid_balances in accounts_with_invalid_balances:
        account_with_invalid_balances['transactions'] = \
            Transaction.objects.filter(budget_id=account_with_invalid_balances['account'].budget_id,
                                       account_id=account_with_invalid_balances['account'].pk,
                                       time_transaction__gte=account_with_invalid_balances[
                                           'account'].balances_valid_until,
                                       ).order_by('time_transaction')

        if len(account_with_invalid_balances['transactions']) > 0:
            account_with_invalid_balances['transaction'] = account_with_invalid_balances['transactions'][0]

        previous_transactions = \
            Transaction.objects.filter(budget_id=account_with_invalid_balances['account'].budget_id,
                                       account_id=account_with_invalid_balances['account'].pk,
                                       time_transaction__lt=account_with_invalid_balances[
                                           'account'].balances_valid_until,
                                       ).order_by('-time_transaction')[:1]
        if len(previous_transactions) > 0:
            account_with_invalid_balances['previous_transaction'] = previous_transactions[0]

        transactions_count = transactions_count + len(account_with_invalid_balances['transactions'])

    # Запускаем главный цикл
    n = 1
    try:
        while True:
            # Отбираем операцию для пересчета в данной итерации - берем самую раннюю из оставшихся по всем счетам
            # Операции перемещения расход в первую очередь при наличии нескольких операций в одно время
            processed_transaction = None
            processed_account_idx = None
            for i, account_with_invalid_balances in enumerate(accounts_with_invalid_balances):
                if account_with_invalid_balances['transaction']:
                    if not processed_transaction:
                        processed_transaction = account_with_invalid_balances['transaction']
                        processed_account_idx = i
                    else:
                        if processed_transaction.time_transaction == \
                                account_with_invalid_balances['transaction'].time_transaction:
                            if account_with_invalid_balances['transaction'].type == 'MO-':
                                processed_transaction = account_with_invalid_balances['transaction']
                                processed_account_idx = i
                        elif processed_transaction.time_transaction > \
                                account_with_invalid_balances['transaction'].time_transaction:
                            processed_transaction = account_with_invalid_balances['transaction']
                            processed_account_idx = i

            # Если не отобрали операцию, значит они закончились - выходим из главного цикла!
            if not processed_transaction:
                break

            # Вытаскиваем обрабатываемую операцию из базы (для консистентности)
            processed_transaction = Transaction.objects.get(pk=processed_transaction.pk)

            # И предыдущую операцию тоже
            previous_transaction = accounts_with_invalid_balances[processed_account_idx]['previous_transaction']
            if previous_transaction:
                previous_transaction = Transaction.objects.get(pk=previous_transaction.pk)

            # Запускаем транзакцию
            with transaction.atomic():

                # 1. Вычисляем остаток по счету в валюте счета для данной операции
                if previous_transaction:
                    processed_transaction.balance_acc_cur = previous_transaction.balance_acc_cur + \
                                                            processed_transaction.amount_acc_cur
                else:
                    processed_transaction.balance_acc_cur = processed_transaction.account.initial_balance + \
                                                            processed_transaction.amount_acc_cur

                # 2. Проверим заведены ли категории у операции, если какой-то причине нет, то заведем по дефолту
                if processed_transaction.type in ['CRE', 'DEB']:
                    transaction_categories = TransactionCategory.objects.filter(transaction_id=processed_transaction.pk)
                    if len(transaction_categories) == 0:
                        new_transaction_category = TransactionCategory()
                        new_transaction_category.transaction = processed_transaction
                        new_transaction_category.amount_acc_cur = processed_transaction.amount_acc_cur
                        if processed_transaction.type == 'CRE':
                            new_transaction_category.category_id = DEFAULT_INC_CATEGORY
                        else:
                            new_transaction_category.category_id = DEFAULT_EXP_CATEGORY
                        new_transaction_category.save()

                # 3. Вычисляем суммы операции в базовых валютах и остатки по счету в базовых валютах
                if processed_transaction.type in ['MO+', 'CRE', 'DEB']:
                    # Все приходные, расходные операции и операции перемещения приход получают рыночные курсы,
                    # суммы операции в базовых валютах через произведения этих курсов на сумму операции в валюте счета,
                    # а остатки в базовых валютах из остатков предыдущей операции с добавлением сумм текущей

                    processed_transaction.rate_base_cur_1 = \
                        CurrencyRate.get_rate(budget_base_currency_1,
                                              processed_transaction.account.currency_id,
                                              processed_transaction.time_transaction)
                    processed_transaction.rate_base_cur_2 = \
                        CurrencyRate.get_rate(budget_base_currency_2,
                                              processed_transaction.account.currency_id,
                                              processed_transaction.time_transaction)

                    processed_transaction.amount_base_cur_1 = \
                        ftod(processed_transaction.amount_acc_cur *
                             processed_transaction.rate_base_cur_1, 2)
                    processed_transaction.amount_base_cur_2 = \
                        ftod(processed_transaction.amount_acc_cur *
                             processed_transaction.rate_base_cur_2, 2)

                    if previous_transaction:
                        processed_transaction.balance_base_cur_1 = previous_transaction.balance_base_cur_1 + \
                                                                   processed_transaction.amount_base_cur_1
                        processed_transaction.balance_base_cur_2 = previous_transaction.balance_base_cur_2 + \
                                                                   processed_transaction.amount_base_cur_2
                    else:
                        processed_transaction.balance_base_cur_1 = \
                            ftod(processed_transaction.account.initial_balance *
                                 CurrencyRate.get_rate(budget_base_currency_1,
                                                       processed_transaction.account.currency_id,
                                                       processed_transaction.time_transaction), 2) + \
                            processed_transaction.amount_base_cur_1
                        processed_transaction.balance_base_cur_2 = \
                            ftod(processed_transaction.account.initial_balance *
                                 CurrencyRate.get_rate(budget_base_currency_2,
                                                       processed_transaction.account.currency_id,
                                                       processed_transaction.time_transaction), 2) + \
                            processed_transaction.amount_base_cur_2

                elif processed_transaction.type in ['MO-']:
                    # Операции перемещения расход получают рыночные курсы по дате операции-приемника, суммы операции в
                    # базовых валютах через произведения этих курсов на инвертированную сумму операции в валюте счета
                    # операции-приемника, а остатки в базовых валютах из остатков предыдущей операции
                    # с добавлением сумм текущей
                    # ВАЖНО! Расчет сумм в базовых валютах производится по сумме в валюте счета операции-приемника,
                    # так как обороты по операциям перемещения должны совпадать, а курсовая разница для операций
                    # покупки-продажи валюты (это когда счет-отправитель и счет-получатель в разных валютах) должна
                    # отражаться на счете-отправителе

                    receiver_transaction = processed_transaction.receiver

                    processed_transaction.rate_base_cur_1 = \
                        CurrencyRate.get_rate(budget_base_currency_1,
                                              receiver_transaction.account.currency_id,
                                              receiver_transaction.time_transaction)
                    processed_transaction.rate_base_cur_2 = \
                        CurrencyRate.get_rate(budget_base_currency_2,
                                              receiver_transaction.account.currency_id,
                                              receiver_transaction.time_transaction)

                    processed_transaction.amount_base_cur_1 = \
                        ftod(-receiver_transaction.amount_acc_cur *
                             processed_transaction.rate_base_cur_1, 2)
                    processed_transaction.amount_base_cur_2 = \
                        ftod(-receiver_transaction.amount_acc_cur *
                             processed_transaction.rate_base_cur_2, 2)

                    if previous_transaction:
                        processed_transaction.balance_base_cur_1 = \
                            previous_transaction.balance_base_cur_1 + \
                            processed_transaction.amount_base_cur_1
                        processed_transaction.balance_base_cur_2 = \
                            previous_transaction.balance_base_cur_2 + \
                            processed_transaction.amount_base_cur_2
                    else:
                        processed_transaction.balance_base_cur_1 = \
                            ftod(processed_transaction.account.initial_balance *
                                 CurrencyRate.get_rate(budget_base_currency_1,
                                                       processed_transaction.account.currency_id,
                                                       processed_transaction.time_transaction), 2) + \
                            processed_transaction.amount_base_cur_1
                        processed_transaction.balance_base_cur_2 = \
                            ftod(processed_transaction.account.initial_balance *
                                 CurrencyRate.get_rate(budget_base_currency_2,
                                                       processed_transaction.account.currency_id,
                                                       processed_transaction.time_transaction), 2) + \
                            processed_transaction.amount_base_cur_2

                elif processed_transaction.type in ['ED+', 'ED-']:
                    # Операции курсовой разницы получают рыночный курс, остаток в базовой валюте как произведение
                    # остатка в валюте счета на рыночный курс, сумма операции в базовой валюте как разницу
                    # остатка от предыдущей операции и вычисленным остатком

                    processed_transaction.rate_base_cur_1 = \
                        CurrencyRate.get_rate(budget_base_currency_1,
                                              processed_transaction.account.currency_id,
                                              processed_transaction.time_transaction)
                    processed_transaction.rate_base_cur_2 = \
                        CurrencyRate.get_rate(budget_base_currency_2,
                                              processed_transaction.account.currency_id,
                                              processed_transaction.time_transaction)

                    new_balance_base_cur_1 = \
                        ftod(processed_transaction.balance_acc_cur *
                             processed_transaction.rate_base_cur_1, 2)
                    new_balance_base_cur_2 = \
                        ftod(processed_transaction.balance_acc_cur *
                             processed_transaction.rate_base_cur_2, 2)

                    if previous_transaction:
                        new_amount_base_cur_1 = new_balance_base_cur_1 - previous_transaction.balance_base_cur_1
                        new_amount_base_cur_2 = new_balance_base_cur_2 - previous_transaction.balance_base_cur_2
                    else:
                        new_amount_base_cur_1 = \
                            new_balance_base_cur_1 - \
                            ftod(processed_transaction.account.initial_balance *
                                 CurrencyRate.get_rate(budget_base_currency_1,
                                                       processed_transaction.account.currency_id,
                                                       datetime(processed_transaction.time_transaction.year,
                                                                processed_transaction.time_transaction.month,
                                                                1, 0, 0, 0, 0, timezone.utc) -
                                                       timedelta(microseconds=1)), 2)
                        new_amount_base_cur_2 = \
                            new_balance_base_cur_2 - \
                            ftod(processed_transaction.account.initial_balance *
                                 CurrencyRate.get_rate(budget_base_currency_2,
                                                       processed_transaction.account.currency_id,
                                                       datetime(processed_transaction.time_transaction.year,
                                                                processed_transaction.time_transaction.month,
                                                                1, 0, 0, 0, 0, timezone.utc) -
                                                       timedelta(microseconds=1)), 2)

                    # Вычисленная курсовая разница записывается в операцию положительной курсовой разницы (ED+),
                    # если она положительна, иначе в операцию отрицательной курсовой разницы (ED-).
                    if processed_transaction.type == 'ED+':

                        if new_amount_base_cur_1 >= 0:
                            processed_transaction.amount_base_cur_1 = new_amount_base_cur_1
                            processed_transaction.balance_base_cur_1 = new_balance_base_cur_1
                        else:
                            processed_transaction.amount_base_cur_1 = ftod(0.00, 2)
                            if previous_transaction:
                                processed_transaction.balance_base_cur_1 = previous_transaction.balance_base_cur_1
                            else:
                                processed_transaction.balance_base_cur_1 = \
                                    ftod(processed_transaction.account.initial_balance *
                                         CurrencyRate.get_rate(budget_base_currency_1,
                                                               processed_transaction.account.currency_id,
                                                               datetime(processed_transaction.time_transaction.year,
                                                                        processed_transaction.time_transaction.month,
                                                                        1, 0, 0, 0, 0, timezone.utc) -
                                                               timedelta(microseconds=1)), 2)

                        if new_amount_base_cur_2 >= 0:
                            processed_transaction.amount_base_cur_2 = new_amount_base_cur_2
                            processed_transaction.balance_base_cur_2 = new_balance_base_cur_2
                        else:
                            processed_transaction.amount_base_cur_2 = ftod(0.00, 2)
                            if previous_transaction:
                                processed_transaction.balance_base_cur_2 = previous_transaction.balance_base_cur_2
                            else:
                                processed_transaction.balance_base_cur_2 = \
                                    ftod(processed_transaction.account.initial_balance *
                                         CurrencyRate.get_rate(budget_base_currency_2,
                                                               processed_transaction.account.currency_id,
                                                               datetime(processed_transaction.time_transaction.year,
                                                                        processed_transaction.time_transaction.month,
                                                                        1, 0, 0, 0, 0, timezone.utc) -
                                                               timedelta(microseconds=1)), 2)

                    elif processed_transaction.type == 'ED-':

                        if new_amount_base_cur_1 <= 0:
                            processed_transaction.amount_base_cur_1 = new_amount_base_cur_1
                            processed_transaction.balance_base_cur_1 = new_balance_base_cur_1
                        else:
                            processed_transaction.amount_base_cur_1 = ftod(0.00, 2)
                            if previous_transaction:
                                processed_transaction.balance_base_cur_1 = previous_transaction.balance_base_cur_1
                            else:
                                processed_transaction.balance_base_cur_1 = \
                                    ftod(processed_transaction.account.initial_balance *
                                         CurrencyRate.get_rate(budget_base_currency_1,
                                                               processed_transaction.account.currency_id,
                                                               datetime(processed_transaction.time_transaction.year,
                                                                        processed_transaction.time_transaction.month,
                                                                        1, 0, 0, 0, 0, timezone.utc) -
                                                               timedelta(microseconds=1)), 2)

                        if new_amount_base_cur_2 <= 0:
                            processed_transaction.amount_base_cur_2 = new_amount_base_cur_2
                            processed_transaction.balance_base_cur_2 = new_balance_base_cur_2
                        else:
                            processed_transaction.amount_base_cur_2 = ftod(0.00, 2)
                            if previous_transaction:
                                processed_transaction.balance_base_cur_2 = previous_transaction.balance_base_cur_2
                            else:
                                processed_transaction.balance_base_cur_2 = \
                                    ftod(processed_transaction.account.initial_balance *
                                         CurrencyRate.get_rate(budget_base_currency_2,
                                                               processed_transaction.account.currency_id,
                                                               datetime(processed_transaction.time_transaction.year,
                                                                        processed_transaction.time_transaction.month,
                                                                        1, 0, 0, 0, 0, timezone.utc) -
                                                               timedelta(microseconds=1)), 2)

                # 4. Сохраним изменения в операции (будет каскад обновлений: категории транзакций и бюджетные регистры
                processed_transaction.save()

                # 5. Вычисляем новую дату валидности у счета и сохраним
                accounts_with_invalid_balances[processed_account_idx]['account'].balances_valid_until = \
                    processed_transaction.time_transaction + timedelta(microseconds=1)
                accounts_with_invalid_balances[processed_account_idx]['account'].save(
                    update_fields=['balances_valid_until'])

            # Все необходимые действия по пересчету с операцией совершены!
            # Берем следующую транзакцию у данного счета
            accounts_with_invalid_balances[processed_account_idx]['previous_transaction'] = processed_transaction
            accounts_with_invalid_balances[processed_account_idx]['idx'] = \
                accounts_with_invalid_balances[processed_account_idx]['idx'] + 1
            if accounts_with_invalid_balances[processed_account_idx]['idx'] >= \
                    len(accounts_with_invalid_balances[processed_account_idx]['transactions']):
                accounts_with_invalid_balances[processed_account_idx]['transaction'] = None
            else:
                next_idx = accounts_with_invalid_balances[processed_account_idx]['idx']
                accounts_with_invalid_balances[processed_account_idx]['transaction'] = \
                    accounts_with_invalid_balances[processed_account_idx]['transactions'][next_idx]

            n = n + 1

        # В конце процедуры у всех счетов, участвующих в пересчете, взводим флаг валидности остатков
        for account_with_invalid_balances in accounts_with_invalid_balances:
            with transaction.atomic():
                account_with_invalid_balances['account'].is_balances_valid = True
                account_with_invalid_balances['account'].save(update_fields=['is_balances_valid'])

        # Еще нужно пересчитать остатки в Бюджетных оборотах счетов

        # Отберем все счета, у которых инвалид в бюджетных оборотах
        accounts_with_invalid_turnovers = Account.objects.filter(budget_id=budget_id, is_turnovers_valid=False)
        for account_with_invalid_turnovers in accounts_with_invalid_turnovers:
            with transaction.atomic():
                last_budget_period = None
                # Сначала получим последний валидный остаток
                previous_account_turnovers = \
                    AccountTurnover.objects.filter(budget_id=budget_id,
                                                   account_id=account_with_invalid_turnovers.pk,
                                                   budget_period__lt=
                                                   account_with_invalid_turnovers.turnovers_valid_until
                                                   ).order_by('-budget_period')[:1]
                account_turnovers = \
                    AccountTurnover.objects.filter(budget_id=budget_id,
                                                   account_id=account_with_invalid_turnovers.pk,
                                                   budget_period__gte=
                                                   account_with_invalid_turnovers.turnovers_valid_until
                                                   ).order_by('budget_period')
                if previous_account_turnovers:
                    # Получим начальный остаток из предыдущего периода
                    previous_balance_base_cur_1 = previous_account_turnovers[0].end_balance_base_cur_1
                    previous_balance_base_cur_2 = previous_account_turnovers[0].end_balance_base_cur_2
                else:
                    # Рассчитаем начальный остаток из начального остатка счета
                    if account_turnovers:
                        previous_balance_base_cur_1 = \
                            ftod(account_with_invalid_turnovers.initial_balance *
                                 CurrencyRate.get_rate(budget_base_currency_1,
                                                       account_with_invalid_turnovers.currency_id,
                                                       account_turnovers[0].budget_period -
                                                       timedelta(days=32)), 2)
                        previous_balance_base_cur_2 = \
                            ftod(account_with_invalid_turnovers.initial_balance *
                                 CurrencyRate.get_rate(budget_base_currency_2,
                                                       account_with_invalid_turnovers.currency_id,
                                                       account_turnovers[0].budget_period -
                                                       timedelta(days=32)), 2)
                    else:
                        previous_balance_base_cur_1 = \
                            ftod(account_with_invalid_turnovers.initial_balance *
                                 CurrencyRate.get_rate(budget_base_currency_1,
                                                       account_with_invalid_turnovers.currency_id,
                                                       account_with_invalid_turnovers.turnovers_valid_until -
                                                       timedelta(days=2)), 2)
                        previous_balance_base_cur_2 = \
                            ftod(account_with_invalid_turnovers.initial_balance *
                                 CurrencyRate.get_rate(budget_base_currency_2,
                                                       account_with_invalid_turnovers.currency_id,
                                                       account_with_invalid_turnovers.turnovers_valid_until -
                                                       timedelta(days=2)), 2)

                # Теперь в цикле пробежим по последующим периодам и пересчитаем остатки через обороты
                # от последнего валидного остатка
                for account_turnover in account_turnovers:
                    account_turnover.begin_balance_base_cur_1 = previous_balance_base_cur_1
                    account_turnover.begin_balance_base_cur_2 = previous_balance_base_cur_2
                    account_turnover.end_balance_base_cur_1 = \
                        previous_balance_base_cur_1 + \
                        account_turnover.credit_turnover_base_cur_1 + \
                        account_turnover.debit_turnover_base_cur_1
                    account_turnover.end_balance_base_cur_2 = \
                        previous_balance_base_cur_2 + \
                        account_turnover.credit_turnover_base_cur_2 + \
                        account_turnover.debit_turnover_base_cur_2
                    account_turnover.save()
                    previous_balance_base_cur_1 = account_turnover.end_balance_base_cur_1
                    previous_balance_base_cur_2 = account_turnover.end_balance_base_cur_2
                    last_budget_period = account_turnover.budget_period

                # Установим на счете флаг валидности бюджетных остатков и новую дату валидности их же
                account_with_invalid_turnovers.is_turnovers_valid = True
                if last_budget_period:
                    turnovers_valid_until = last_budget_period + timedelta(days=32)
                    turnovers_valid_until = datetime(turnovers_valid_until.year, turnovers_valid_until.month,
                                                     1, 0, 0, 0, 0, timezone.utc)
                    account_with_invalid_turnovers.turnovers_valid_until = turnovers_valid_until
                account_with_invalid_turnovers.save()

    except Exception as e:
        print('Что-то в главном цикле процедуры пересчета остатков пошло не так: ' + str(e))

    return redirect(return_url)


@login_required
def account_transactions_without_join(request, budget_id, return_url):
    """
    Функция списка операций перемещения без связи
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    if budget_id != request.user.profile.budget.pk:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")

    if return_url[0:1] != '/':
        return_url = '/' + return_url

    accounts_with_unlinked_transactions = \
        (Account.objects.distinct()
         .filter(budget_id=budget_id,
                 transactions__type__icontains='MO',
                 transactions__sender__isnull=True,
                 transactions__receiver__isnull=True)
         .order_by('name')
         )

    if len(accounts_with_unlinked_transactions) == 0:
        return redirect(return_url)

    return render(request, 'main/account_transactions_without_join.html',
                  get_u_context(request,
                                {'title': 'Счета с операциями перемещения без связи',
                                 'accounts_with_unlinked_transactions': accounts_with_unlinked_transactions,
                                 'work_menu': True,
                                 'account_selected': -10,
                                 'selected_menu': 'account_transactions',
                                 'return_url': return_url,
                                 }))


@login_required
def load_transactions(request, account_id, return_url):
    """
    Функция загрузки операций по счету из файла
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')

    account = get_object_or_404(Account, pk=account_id)

    if account.budget != request.user.profile.budget:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")

    if return_url[0:1] != '/':
        return_url = '/' + return_url

    if request.method == 'POST':
        form = LoadTransactionForm(account=account, data=request.POST, files=request.FILES)

        if form.is_valid():
            # Откроем скаченный файл
            csv_file = StringIO(request.FILES['transactions_file'].read().decode('utf-8-sig'))

            # Зададим начальный список полей в первую строку лога загрузки
            transaction_loading_log = [['Статус', '№', 'Тип']]

            # На основе открытого файла зададим итератор-словарь rows
            if request.POST['are_field_headers'] == '1':
                # Задаем csv итератор-словарь без указания заголовков
                if request.POST['string_delimiter']:
                    rows = csv.DictReader(csv_file,
                                          restkey='another_fields',
                                          restval=None,
                                          delimiter=request.POST['column_delimiter'],
                                          quotechar=request.POST['string_delimiter'])
                else:
                    rows = csv.DictReader(csv_file,
                                          restkey='another_fields',
                                          restval=None,
                                          delimiter=request.POST['column_delimiter'])
                is_need_check_headers = True
                row_idx = 2
            else:
                # Задаем csv итератор-словарь с заголовками, указанными пользователем
                headers = form.headers
                if request.POST['string_delimiter']:
                    rows = csv.DictReader(csv_file,
                                          fieldnames=headers,
                                          restkey='another_fields',
                                          restval=None,
                                          delimiter=request.POST['column_delimiter'],
                                          quotechar=request.POST['string_delimiter'])
                else:
                    rows = csv.DictReader(csv_file,
                                          fieldnames=headers,
                                          restkey='another_fields',
                                          restval=None,
                                          delimiter=request.POST['column_delimiter'])
                # Расширим первую строку лога заголовками полей, указанными пользователем
                transaction_loading_log[0].extend(headers)
                is_need_check_headers = False
                row_idx = 1

            is_error = False

            # Получим форматы ввода даты-времени допустимые в данной локации и сформируем подсказку для ошибок
            datetime_formats = formats.get_format("DATETIME_INPUT_FORMATS", lang=translation.get_language())
            datetime_formats.append(datetime_formats[0][:8])
            example_datetime = datetime.utcnow()
            valid_datetime_formats = 'Допустимые форматы даты-времени:'
            for datetime_format in datetime_formats:
                valid_datetime_formats += f"<br>{datetime_format}: {example_datetime.strftime(datetime_format)}"

            # Цикл по строкам (операциям)
            for row in rows:
                if is_need_check_headers:
                    # Проверяем действительное наличие заголовков в части обязательных полей
                    headers = row.keys()
                    for trf in TRANSACTION_REQUIRED_FIELDS:
                        if trf[0] not in headers:
                            form.add_error('are_field_headers',
                                           forms.ValidationError('В заголовках файла нет обязательного поля - ' +
                                                                 trf[1] + ' (' + trf[0] + ')'))
                            is_error = True
                    if is_error:
                        break
                    is_need_check_headers = False
                    # Расширим первую строку лога заголовками полей, полученными из первой строки файла
                    transaction_loading_log[0].extend(headers)

                # Добавим пустую строчку в лог, соответствующую строке файла
                transaction_loading_log.append([None, row_idx, {}, {}])
                log_idx = len(transaction_loading_log) - 1

                # Вытаскиваем значения из строки файла, нормализуем их
                # В случае ошибок взводим флаги ошибок для каждого поля, записываем в лог ошибку и подсказку

                # 1. ОБЯЗАТЕЛЬНОЕ ПОЛЕ! Дата-время операции  - time_transaction
                is_time_transaction_error = True
                time_transaction_str = row.get('time_transaction', '')
                time_transaction = None
                time_zone = None
                transaction_loading_log[log_idx][3]['time_transaction'] = {'value': time_transaction_str}
                # Попробуем распарсить дату-время из файла допустимыми форматами в данной локации
                for datetime_format in datetime_formats:
                    try:
                        time_transaction = datetime.strptime(time_transaction_str, datetime_format)
                        time_zone = ftod(request.POST['transactions_time_zone'], 2)
                        # Приводим дату-время к UTC
                        if time_transaction.hour != 0 or time_transaction.minute != 0 or \
                                time_transaction.second != 0 or time_transaction.microsecond != 0:
                            time_transaction = time_transaction - timedelta(hours=float(time_zone))
                        time_transaction = datetime(time_transaction.year,
                                                    time_transaction.month,
                                                    time_transaction.day,
                                                    time_transaction.hour,
                                                    time_transaction.minute,
                                                    time_transaction.second,
                                                    time_transaction.microsecond,
                                                    timezone.utc)
                        is_time_transaction_error = False
                        break
                    except Exception as e:
                        pass
                if is_time_transaction_error:
                    transaction_loading_log[log_idx][3]['time_transaction']['error'] = 'ошибка формата даты-времени'
                    transaction_loading_log[log_idx][3]['time_transaction']['tip'] = valid_datetime_formats
                elif time_transaction < MIN_TRANSACTION_DATETIME or time_transaction > MAX_TRANSACTION_DATETIME:
                    is_time_transaction_error = True
                    time_transaction = None
                    transaction_loading_log[log_idx][3]['time_transaction']['error'] = 'ошибка даты-времени'
                    transaction_loading_log[log_idx][3]['time_transaction']['tip'] = \
                        f"Допускаются даты в интервале<br>от {MIN_TRANSACTION_DATETIME}<br>" \
                        f"до {MAX_TRANSACTION_DATETIME}"

                # 2. ОБЯЗАТЕЛЬНОЕ ПОЛЕ! Сумма операции в валюте счета - amount_acc_cur
                is_amount_acc_cur_error = False
                amount_acc_cur_str = row.get('amount_acc_cur', '')
                amount_acc_cur_str = amount_acc_cur_str.replace(' ', '')
                amount_acc_cur_str = amount_acc_cur_str.replace(',', '.')
                amount_acc_cur = None
                transaction_loading_log[log_idx][3]['amount_acc_cur'] = {'value': amount_acc_cur_str}
                try:
                    amount_acc_cur = ftod(amount_acc_cur_str, 2)
                except Exception as e:
                    is_amount_acc_cur_error = True
                    transaction_loading_log[log_idx][3]['amount_acc_cur']['error'] = 'ошибка значения суммы'
                    transaction_loading_log[log_idx][3]['amount_acc_cur']['tip'] = 'Допускаются цифры, минус,<br>' \
                                                                                   'точка или запятая'

                # 3. ОБЯЗАТЕЛЬНОЕ ПОЛЕ! Признак операции-перемещения - movement_flag
                is_movement_flag_error = False
                movement_flag_str = row.get('movement_flag', None)
                movement_flag = None
                transaction_loading_log[log_idx][3]['movement_flag'] = {'value': movement_flag_str}
                if movement_flag_str.lower() in ['0', 'false', 'f', 'нет', 'н']:
                    movement_flag = False
                elif movement_flag_str.lower() in ['1', 'true', 't', 'да', 'д']:
                    movement_flag = True
                else:
                    is_movement_flag_error = True
                    transaction_loading_log[log_idx][3]['movement_flag']['error'] = 'ошибка логического значения'
                    transaction_loading_log[log_idx][3]['movement_flag']['tip'] = 'Допустимые значения:<br>' \
                                                                                  '0, Нет, False, 1, Да, True'

                # 4. ОБЯЗАТЕЛЬНОЕ ПОЛЕ! Категория операции - category
                is_category_error = False
                category_str = row.get('category', '')
                category = None
                transaction_loading_log[log_idx][3]['category'] = {'value': category_str}
                if not movement_flag:
                    try:
                        category = Category.objects.get(name=category_str)
                        if not category.parent:
                            category = None
                            raise
                    except Exception as e:
                        is_category_error = True
                        transaction_loading_log[log_idx][3]['category']['error'] = 'категория не найдена'
                        transaction_loading_log[log_idx][3]['category']['tip'] = \
                            'Допустимые значения<br>смотри&nbsp;<a href="/static/main/upload/hamsterock-loading.xlsx"' \
                            ' download="hamsterock-loading">здесь</a>'

                # 5. Объект бюджета - budget_object
                is_budget_object_error = False
                budget_object_str = row.get('budget_object', '')
                budget_object = None
                budget_object_created = None
                if budget_object_str:
                    transaction_loading_log[log_idx][3]['budget_object'] = {'value': budget_object_str}
                    try:
                        budget_object, budget_object_created = BudgetObject.objects.get_or_create(
                            budget_id=account.budget_id, name=budget_object_str)
                    except Exception as e:
                        is_budget_object_error = True
                        transaction_loading_log[log_idx][3]['budget_object']['error'] = \
                            'объект бюджета не был найден<br>и не смог создаться'
                        transaction_loading_log[log_idx][3]['budget_object']['tip'] = 'Обратитесь к администратору'

                # В случае, когда получили валидную категорию (базовую) и валидный непустой объект бюджета нужно
                # получить категорию с бюджетным объектом (это отдельная строка в списке категорий)
                # Вызываем Category.get_category_with_object(), которая либо вернет уже существующую категорию,
                # либо вновь созданную
                if not is_category_error and not is_budget_object_error and budget_object:
                    try:
                        c_id = Category.get_category_with_object(account.budget, category.pk,
                                                                 budget_object.pk, request.user)
                        category = Category.objects.get(pk=c_id)
                    except Exception as e:
                        pass

                # На основе значений признака операции-перемещения и типа категории вычисляем тип операции
                if amount_acc_cur is None or movement_flag is None:
                    transaction_type = None
                elif movement_flag:
                    transaction_type = 'MO+' if amount_acc_cur >= 0 else 'MO-'
                elif category is None:
                    transaction_type = None
                else:
                    transaction_type = 'CRE' if category.type == 'INC' else 'DEB'
                transaction_loading_log[log_idx][2] = {'value': transaction_type}

                # 6. Валюта операции - currency
                is_currency_error = False
                currency_str = row.get('currency', '')
                currency = None
                if currency_str:
                    transaction_loading_log[log_idx][3]['currency'] = {'value': currency_str}
                    try:
                        currency = Currency.objects.get(iso_code=currency_str)
                    except Exception as e:
                        is_category_error = True
                        transaction_loading_log[log_idx][3]['currency']['error'] = 'валюта не найдена'
                        transaction_loading_log[log_idx][3]['currency']['tip'] = \
                            'Допустимые значения<br>смотри&nbsp;<a href="/static/main/upload/hamsterock-loading.xlsx"' \
                            ' download="hamsterock-loading">здесь</a>'
                else:
                    currency = account.currency

                # 7. Сумма операции в валюте операции - amount
                is_amount_error = False
                amount_str = row.get('amount', '')
                amount = None
                if amount_str:
                    amount_str = amount_str.replace(' ', '')
                    amount_str = amount_str.replace(',', '.')
                    transaction_loading_log[log_idx][3]['amount'] = {'value': amount_str}
                    try:
                        amount = ftod(amount_str, 2)
                    except Exception as e:
                        is_amount_error = True
                        transaction_loading_log[log_idx][3]['amount']['error'] = 'ошибка значения суммы'
                        transaction_loading_log[log_idx][3]['amount']['tip'] = 'Допускаются цифры, минус,<br>' \
                                                                               'точка или запятая'
                else:
                    if amount_acc_cur:
                        if currency == account.currency or currency is None or time_transaction is None:
                            amount = ftod(amount_acc_cur, 2)
                        else:
                            amount = ftod(amount_acc_cur *
                                          CurrencyRate.get_rate(currency, account.currency, time_transaction), 2)

                # 8. Проект - project
                is_project_error = False
                project_str = row.get('project', '')
                project = None
                if project_str:
                    transaction_loading_log[log_idx][3]['project'] = {'value': project_str}
                    try:
                        project, project_created = Project.objects.get_or_create(budget_id=account.budget_id,
                                                                                 name=project_str)
                    except Exception as e:
                        is_project_error = True
                        transaction_loading_log[log_idx][3]['project']['error'] = 'проект не был найден<br>' \
                                                                                  'и не смог создаться'
                        transaction_loading_log[log_idx][3]['project']['tip'] = 'Обратитесь к администратору'

                # 9. Год периода бюджета - budget_year
                is_budget_year_error = False
                budget_year_str = row.get('budget_year', '')
                budget_year = None
                if budget_year_str:
                    transaction_loading_log[log_idx][3]['budget_year'] = {'value': budget_year_str}
                    try:
                        budget_year = int(budget_year_str)
                        if not (MIN_BUDGET_YEAR <= budget_year <= MAX_BUDGET_YEAR):
                            budget_year = None
                            raise
                    except Exception as e:
                        is_budget_year_error = True
                        transaction_loading_log[log_idx][3]['budget_year']['error'] = 'ошибка значения года'
                        transaction_loading_log[log_idx][3]['budget_year']['tip'] = \
                            f"Допускаются целые числа<br>в интервале от {MIN_BUDGET_YEAR} до {MAX_BUDGET_YEAR}"
                else:
                    try:
                        budget_year = time_transaction.year
                    except Exception as e:
                        budget_year = None

                # 10. Месяц периода бюджета - budget_month
                is_budget_month_error = False
                budget_month_str = row.get('budget_month', '')
                budget_month = None
                if budget_month_str:
                    transaction_loading_log[log_idx][3]['budget_month'] = {'value': budget_month_str}
                    try:
                        budget_month = int(budget_month_str)
                        if not (1 <= budget_month <= 12):
                            budget_month = None
                            raise
                    except Exception as e:
                        is_budget_month_error = True
                        transaction_loading_log[log_idx][3]['budget_month']['error'] = 'ошибка значения месяца'
                        transaction_loading_log[log_idx][3]['budget_month']['tip'] = 'Допускаются целые числа<br>' \
                                                                                     'в интервале от 1 до 12'
                else:
                    try:
                        budget_month = time_transaction.month
                    except Exception as e:
                        budget_month = None

                # 11. Описание операции от банка - bank_description
                bank_description = row.get('bank_description', None)
                if bank_description:
                    transaction_loading_log[log_idx][3]['bank_description'] = {'value': bank_description}

                # 12. Категория операции от банка - bank_category
                bank_category = row.get('bank_category', None)
                if bank_category:
                    transaction_loading_log[log_idx][3]['bank_category'] = {'value': bank_category}

                # 13. MCC код от банка - mcc_code
                mcc_code = row.get('mcc_code', None)
                if mcc_code:
                    transaction_loading_log[log_idx][3]['mcc_code'] = {'value': mcc_code}

                # 14. Место совершения операции - place
                place = row.get('place', None)
                if place:
                    transaction_loading_log[log_idx][3]['place'] = {'value': place}

                # 15. Описание операции - description
                description = row.get('description', None)
                if description:
                    transaction_loading_log[log_idx][3]['description'] = {'value': description}

                # Развилка по наличию ошибок или их отсутствию
                if not (is_time_transaction_error or is_amount_acc_cur_error or is_movement_flag_error or
                        is_category_error or is_currency_error or is_amount_error or is_project_error or
                        is_budget_year_error or is_budget_month_error):
                    # Ошибок нет
                    budget = account.budget
                    user_create = request.user
                    user_update = request.user

                    # Посмотрим есть ли такая операция уже в системе (время + тип + сумма)
                    exist_the_same_transactions = \
                        Transaction.objects.filter(budget_id=budget.pk, account_id=account.pk,
                                                   time_transaction=time_transaction, type=transaction_type,
                                                   amount_acc_cur=amount_acc_cur)
                    if exist_the_same_transactions:
                        transaction_loading_log[log_idx][2]['error'] = 'такая операция<br>уже существует'
                        transaction_loading_log[log_idx][0] = 0
                    else:
                        # Такой операции нет - создаем ее и категорию к ней
                        try:
                            with transaction.atomic():
                                new_transaction = Transaction()
                                new_transaction.budget = budget
                                new_transaction.account = account
                                new_transaction.type = transaction_type
                                new_transaction.time_transaction = time_transaction
                                new_transaction.time_zone = time_zone
                                new_transaction.amount_acc_cur = amount_acc_cur
                                new_transaction.currency = currency
                                new_transaction.amount = amount
                                new_transaction.budget_year = budget_year
                                new_transaction.budget_month = budget_month
                                new_transaction.place = place
                                new_transaction.description = description
                                new_transaction.mcc_code = mcc_code
                                new_transaction.banks_category = bank_category
                                new_transaction.banks_description = bank_description
                                new_transaction.project = project
                                new_transaction.user_create = user_create
                                new_transaction.user_update = user_update
                                new_transaction.save()
                                if transaction_type in ['CRE', 'DEB']:
                                    new_transaction_category = TransactionCategory()
                                    new_transaction_category.transaction = new_transaction
                                    new_transaction_category.category = category
                                    new_transaction_category.amount_acc_cur = amount_acc_cur
                                    new_transaction_category.budget_year = budget_year
                                    new_transaction_category.budget_month = budget_month
                                    new_transaction_category.project = project
                                    new_transaction_category.save()
                                transaction_loading_log[log_idx][0] = 1
                        except Exception as e:
                            transaction_loading_log[log_idx][2]['error'] = 'операция не смогла<br>быть загружена'
                            transaction_loading_log[log_idx][0] = 0
                else:
                    transaction_loading_log[log_idx][0] = 0

                row_idx += 1

            # Если не было ошибки на уровне наличия обязательных полей в файле, то показываем пользователю лог загрузки
            if not is_error:
                return render(request, 'main/transaction_loading_log.html',
                              get_u_context(request,
                                            {'title': 'Протокол загрузки операций из файла по счету/кошельку - ' +
                                                      str(account),
                                             'file': request.FILES['transactions_file'].name,
                                             'header_loading_log': transaction_loading_log[0],
                                             'transaction_loading_log': transaction_loading_log[1:],
                                             'work_menu': True,
                                             'account_selected': account.id,
                                             'selected_menu': 'account_transactions',
                                             'return_url': return_url}))
    else:
        form = LoadTransactionForm(account=account)

    last_transactions = \
        Transaction.objects.filter(budget_id=account.budget.pk, account_id=account.pk).exclude(
            type__in=['ED+', 'ED-']).order_by('-time_transaction')[:3]

    return render(request, 'main/transaction_load.html',
                  get_u_context(request,
                                {'title': 'Загрузка операций из файла по счету/кошельку - ' + str(account),
                                 'form': form,
                                 'account_balance': account.balance,
                                 'account_available_balance': account.balance + account.credit_limit,
                                 'account_credit_limit': account.credit_limit,
                                 'account_type': account.type,
                                 'account_budget': account.budget.pk,
                                 'account_currency_id': account.currency.pk,
                                 'account_currency_iso': account.currency.iso_code,
                                 'last_transactions': last_transactions,
                                 'work_menu': True,
                                 'account_selected': account.id,
                                 'selected_menu': 'account_transactions',
                                 'return_url': return_url}))


@login_required
def annual_budget(request, year, currency_id):
    """
    Функция отображения и планирования годового бюджета
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    else:
        budget_id = request.user.profile.budget_id

    budget_base_currency_1 = request.user.profile.budget.base_currency_1_id

    # Проверим, есть ли в Project запись нулевая запись - она нужна для планирования проектных расходов
    # Если нет, то создадим
    if not Project.objects.filter(pk=0, budget_id__isnull=True):
        Project.objects.create(id=0, name='...для плана', )

    # Все данные бюджета оформим в виде словаря, создадим заготовку
    budget_items = dict()

    # Добавляем пустой раздел 1 "Остатки на начало"
    budget_items['opening_balance'] = \
        {0: {'item': '1.',
             'name': 'ОСТАТКИ НА НАЧАЛО',
             'parent_parent_id': 0,
             'parent_id': 0,
             'is_empty': False,
             'values': {m: {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                            'execution_percentage': ftod(0.0000, 4)}
                        for m in range(1, 13)}
             }
         }
    budget_items['opening_balance'][0]['values']['year'] = \
        {'planned_balance': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
         'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}

    # Добавляем категории счетов/кошельков из константы ACCOUNT_TYPES и сами счета/кошельки
    n_type_category = 1
    for account_type_category in ACCOUNT_TYPES[1:]:
        budget_items['opening_balance'][account_type_category[0]] = \
            {'item': '1.' + str(n_type_category) + '.',
             'name': account_type_category[0],
             'parent_parent_id': 0,
             'parent_id': 0,
             'is_empty': True,
             'values': {m: {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                            'execution_percentage': ftod(0.0000, 4)}
                        for m in range(1, 13)}
             }
        budget_items['opening_balance'][account_type_category[0]]['values']['year'] = \
            {'planned_balance': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
             'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
        n_type = 1
        for account_type in account_type_category[1]:
            budget_items['opening_balance'][account_type[0]] = \
                {'item': '1.' + str(n_type_category) + '.' + str(n_type) + '.',
                 'name': account_type[1],
                 'parent_parent_id': 0,
                 'parent_id': account_type_category[0],
                 'is_empty': True,
                 'values': {m: {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                                'execution_percentage': ftod(0.0000, 4)}
                            for m in range(1, 13)}
                 }
            budget_items['opening_balance'][account_type[0]]['values']['year'] = \
                {'planned_balance': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                 'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
            accounts = Account.objects.filter(budget_id=budget_id, type=account_type[0]).order_by('name')
            n_account = 1
            for account in accounts:
                budget_items['opening_balance'][account.id] = \
                    {'item': '1.' + str(n_type_category) + '.' + str(n_type) + '.' + str(n_account) + '.',
                     'name': str(account),
                     'parent_parent_id': account_type_category[0],
                     'parent_id': account_type[0],
                     'is_empty': True,
                     'values': {m: {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                                    'execution_percentage': ftod(0.0000, 4) }
                                for m in range(1, 13)}
                     }
                budget_items['opening_balance'][account.id]['values']['year'] = \
                    {'planned_balance': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                     'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
                n_account += 1
            n_type += 1
        n_type_category += 1

    # Добавляем пустой раздел 2 "Доходы" (результирующая строка со столбцами по месяцам и году в целом)
    # Значения План/Факт/% исполнения представляется в трех разрезах: Общая сумма / Текущий приход / Проектный приход
    budget_items['income_items'] = \
        {0: {'item': '2.',
             'name': 'ДОХОДЫ',
             'parent_id': 0,
             'is_empty': False,
             'hidden_children': {},
             'values': {m: {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                                'execution_percentage': ftod(0.0000, 4)
                                } for p in ['all', 'project', 'non_project']} for m in range(1, 13)}
             }
         }
    budget_items['income_items'][0]['values']['year'] = \
        {p: {'planned_value': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
             'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
             } for p in ['all', 'project', 'non_project']
         }

    # Дополняем раздел 2 "Доходы" категориями из справочника из базы данных
    for cat, dic in tree_item_iterator(Category.objects.filter(type='INC')):
        if not cat.budget or cat.budget.pk == budget_id:
            try:
                parent_id = cat.parent.id
            except Exception as e:
                parent_id = 0
            budget_items['income_items'][cat.id] = \
                {'item': '2.' + cat.item,
                 'name': cat.name,
                 'parent_id': parent_id,
                 'is_empty': True,
                 'hidden_children': {},
                 'values': {}
                 }

    # Добавляем пустой раздел 3 "Расходы" (результирующая строка со столбцами по месяцам и году в целом)
    # Значения План/Факт/% исполнения представляется в трех разрезах: Общая сумма / Текущий расход / Проектный расход
    budget_items['expenditure_items'] = \
        {0: {'item': '3.',
             'name': 'РАСХОДЫ',
             'parent_id': 0,
             'is_empty': False,
             'hidden_children': {},
             'values': {m: {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                                'execution_percentage': ftod(0.0000, 4)
                                } for p in ['all', 'project', 'non_project']} for m in range(1, 13)}
             }
         }
    budget_items['expenditure_items'][0]['values']['year'] = \
        {p: {'planned_value': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
             'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
             } for p in ['all', 'project', 'non_project']
         }

    # Дополняем раздел 3 "Расходы" категориями из справочника из базы данных
    for cat, dic in tree_item_iterator(Category.objects.filter(type='EXP')):
        if not cat.budget or cat.budget.pk == budget_id:
            try:
                parent_id = cat.parent.id
            except Exception as e:
                parent_id = 0
            budget_items['expenditure_items'][cat.id] = \
                {'item': '3.' + cat.item,
                 'name': cat.name,
                 'parent_id': parent_id,
                 'is_empty': True,
                 'hidden_children': {},
                 'values': {}
                 }

    # Добавляем пустой раздел 4 "Остатки на конец"
    budget_items['closing_balance'] = \
        {0: {'item': '4.',
             'name': 'ОСТАТКИ НА КОНЕЦ',
             'parent_parent_id': 0,
             'parent_id': 0,
             'is_empty': False,
             'values': {m: {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                            'execution_percentage': ftod(0.0000, 4)}
                        for m in range(1, 13)}
             }
         }
    budget_items['closing_balance'][0]['values']['year'] = \
        {'planned_balance': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
         'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}

    # Добавляем категории счетов/кошельков из константы ACCOUNT_TYPES и сами счета/кошельки
    n_type_category = 1
    for account_type_category in ACCOUNT_TYPES[1:]:
        budget_items['closing_balance'][account_type_category[0]] = \
            {'item': '4.' + str(n_type_category) + '.',
             'name': account_type_category[0],
             'parent_parent_id': 0,
             'parent_id': 0,
             'is_empty': True,
             'values': {m: {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                            'execution_percentage': ftod(0.0000, 4)}
                        for m in range(1, 13)}
             }
        budget_items['closing_balance'][account_type_category[0]]['values']['year'] = \
            {'planned_balance': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
             'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
        n_type = 1
        for account_type in account_type_category[1]:
            budget_items['closing_balance'][account_type[0]] = \
                {'item': '4.' + str(n_type_category) + '.' + str(n_type) + '.',
                 'name': account_type[1],
                 'parent_parent_id': 0,
                 'parent_id': account_type_category[0],
                 'is_empty': True,
                 'values': {m: {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                                'execution_percentage': ftod(0.0000, 4)}
                            for m in range(1, 13)}
                 }
            budget_items['closing_balance'][account_type[0]]['values']['year'] = \
                {'planned_balance': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                 'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
            accounts = Account.objects.filter(budget_id=budget_id, type=account_type[0]).order_by('name')
            n_account = 1
            for account in accounts:
                budget_items['closing_balance'][account.id] = \
                    {'item': '4.' + str(n_type_category) + '.' + str(n_type) + '.' + str(n_account) + '.',
                     'name': str(account),
                     'parent_parent_id': account_type_category[0],
                     'parent_id': account_type[0],
                     'is_empty': True,
                     'values': {m: {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                                    'execution_percentage': ftod(0.0000, 4)}
                                for m in range(1, 13)}
                     }
                budget_items['closing_balance'][account.id]['values']['year'] = \
                    {'planned_balance': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                     'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
                n_account += 1
            n_type += 1
        n_type_category += 1

    # Добавляем пустой раздел 5 "Сальдо" (одна результирующая строка со столбцами по месяцам и году в целом)
    budget_items['difference'] = \
        {'item': '5.',
         'name': 'САЛЬДО',
         'values': {m: {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                            'execution_percentage': ftod(0.0000, 4)
                            } for p in ['all', 'project', 'non_project']} for m in range(1, 13)}
         }
    budget_items['difference']['values']['year'] = \
        {p: {'planned_value': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
             'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
             } for p in ['all', 'project', 'non_project']
         }

    # Вытаскиваем из базы данных для заданного бюджета регистры заданного года
    budget_registers = \
        BudgetRegister.objects.filter(budget_id=budget_id, budget_year=year).select_related('category', 'project')

    # Заполняем разделы 2 и 3 словаря данными из вытащенных регистров
    for budget_register in budget_registers:
        # Определяем приход или расход
        idx_budget = 'income_items' if budget_register.category.type == 'INC' else 'expenditure_items'

        # Определяем суммы исходя из валюты
        planned_value = ftod(budget_register.planned_amount_base_cur_1, 2) \
            if currency_id == budget_base_currency_1 \
            else ftod(budget_register.planned_amount_base_cur_2, 2)
        actual_value = ftod(budget_register.actual_amount_base_cur_1, 2) \
            if currency_id == budget_base_currency_1 \
            else ftod(budget_register.actual_amount_base_cur_2, 2)

        # Если суммы нулевые, то не будем добавлять строчку в массив, кроме курсовых разниц
        if budget_register.category_id not in [POSITIVE_EXCHANGE_DIFFERENCE, NEGATIVE_EXCHANGE_DIFFERENCE] and \
                planned_value == ftod(0.00, 2) and actual_value == ftod(0.00, 2):
            continue

        # Для расходов снесем минуса для приятности глаз токмо
        if budget_register.category.type == 'EXP':
            planned_value = -planned_value
            actual_value = -actual_value

        month = budget_register.budget_month
        category = budget_register.category_id
        parent_category = budget_register.category.parent_id
        project = budget_register.project

        # Проставим флаг заполненности категории
        budget_items[idx_budget][category]['is_empty'] = False
        budget_items[idx_budget][parent_category]['is_empty'] = False

        # Если по категории массив со значениями пустой, то задефолтим
        if not budget_items[idx_budget][category]['values']:
            budget_items[idx_budget][category]['values'] = \
                {m: {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                         'execution_percentage': ftod(0.0000, 4)
                         } for p in ['all', 'project', 'non_project']} for m in range(1, 13)}
            budget_items[idx_budget][category]['values']['year'] = \
                {p: {'planned_value': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                     'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
                     } for p in ['all', 'project', 'non_project']
                 }

        # Если по родительской категории массив со значениями пустой, то задефолтим
        if not budget_items[idx_budget][parent_category]['values']:
            budget_items[idx_budget][parent_category]['values'] = \
                 {m: {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                          'execution_percentage': ftod(0.0000, 4)
                          } for p in ['all', 'project', 'non_project']} for m in range(1, 13)}
            budget_items[idx_budget][parent_category]['values']['year'] = \
                {p: {'planned_value': ftod(0.00, 2), 'current_plan': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                     'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
                     } for p in ['all', 'project', 'non_project']
                 }

        # Перебор по Регистрам /Категория (категория регистра, родительская категория, приход или расход в целом)
        for c in [category, parent_category, 0]:
            # Перебор по Регистрам /Месяц или Год (месяц регистра или год в целом)
            for m in [month, 'year']:
                # Регистр /общая сумма
                budget_items[idx_budget][c]['values'][m]['all']['planned_value'] += planned_value
                budget_items[idx_budget][c]['values'][m]['all']['actual_value'] += actual_value
                budget_items[idx_budget][c]['values'][m]['all']['execution_percentage'] = \
                    get_execution_percentage(budget_items[idx_budget][c]['values'][m]['all']['planned_value'],
                                             budget_items[idx_budget][c]['values'][m]['all']['actual_value'])
                # Регистр /текущие или проектные
                if project:
                    budget_items[idx_budget][c]['values'][m]['project']['planned_value'] += planned_value
                    budget_items[idx_budget][c]['values'][m]['project']['actual_value'] += actual_value
                    budget_items[idx_budget][c]['values'][m]['project']['execution_percentage'] = \
                        get_execution_percentage(budget_items[idx_budget][c]['values'][m]['project']['planned_value'],
                                                 budget_items[idx_budget][c]['values'][m]['project']['actual_value'])
                    if project.id:
                        if not budget_items[idx_budget][c]['values'][m].get('projects', None):
                            budget_items[idx_budget][c]['values'][m]['projects'] = {}
                        if not budget_items[idx_budget][c]['values'][m]['projects'].get(project.id, None):
                            budget_items[idx_budget][c]['values'][m]['projects'][project.id] = \
                                {'name': project.name, 'actual_value': actual_value}
                        else:
                            budget_items[idx_budget][c]['values'][m]['projects'][project.id]['actual_value'] += \
                                actual_value
                else:
                    budget_items[idx_budget][c]['values'][m]['non_project']['planned_value'] += planned_value
                    budget_items[idx_budget][c]['values'][m]['non_project']['actual_value'] += actual_value
                    budget_items[idx_budget][c]['values'][m]['non_project']['execution_percentage'] = \
                        get_execution_percentage(
                            budget_items[idx_budget][c]['values'][m]['non_project']['planned_value'],
                            budget_items[idx_budget][c]['values'][m]['non_project']['actual_value']
                        )

    # Снесем категории с пустыми массивами значений, предварительно добавив их в список для выбора по кнопке "+"
    # Родительские категории не трогаем
    for idx_budget in ['income_items', 'expenditure_items']:
        for key in list(budget_items[idx_budget].keys()):
            if not budget_items[idx_budget][key]['values']:
                parent_category_id = budget_items[idx_budget][key]['parent_id']
                if key != POSITIVE_EXCHANGE_DIFFERENCE and key != NEGATIVE_EXCHANGE_DIFFERENCE:
                    budget_items[idx_budget][parent_category_id]['hidden_children'][key] = \
                        budget_items[idx_budget][key]['item'] + ' ' + budget_items[idx_budget][key]['name']
                if parent_category_id:
                    budget_items[idx_budget].pop(key, None)
                else:
                    budget_items[idx_budget][key]['values'] = \
                        {m: {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                                 'execution_percentage': ftod(0.0000, 4)
                                 } for p in ['all', 'project', 'non_project']} for m in range(1, 13)}
                    budget_items[idx_budget][key]['values']['year'] = \
                        {p: {'planned_value': ftod(0.00, 2), 'current_plan': ftod(0.00, 2),
                             'actual_value': ftod(0.00, 2),
                             'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
                             } for p in ['all', 'project', 'non_project']
                         }

    # Количество месяцев, для определения текущего плана и среднемесячных значений
    calculate_month = datetime.utcnow().month if year == datetime.utcnow().year else 12

    # Посчитаем для разделов 2 и 3 текущий план для года, его исполнение и среднее месячное
    current_plan = dict()
    for idx_budget in ['income_items', 'expenditure_items']:
        for key in budget_items[idx_budget].keys():
            if calculate_month == 12:
                for p in ['all', 'project', 'non_project']:
                    current_plan[p] = budget_items[idx_budget][key]['values']['year'][p]['planned_value']
            else:
                for p in ['all', 'project', 'non_project']:
                    current_plan[p] = ftod(0.00, 2)
                for m in range(1, calculate_month + 1):
                    for p in ['all', 'project', 'non_project']:
                        current_plan[p] += budget_items[idx_budget][key]['values'][m][p]['planned_value']

            for p in ['all', 'project', 'non_project']:
                budget_items[idx_budget][key]['values']['year'][p]['current_plan'] = current_plan[p]
                budget_items[idx_budget][key]['values']['year'][p]['execution_percentage'] = \
                    get_execution_percentage(budget_items[idx_budget][key]['values']['year'][p]['current_plan'],
                                             budget_items[idx_budget][key]['values']['year'][p]['actual_value'])
                budget_items[idx_budget][key]['values']['year'][p]['average_value'] = \
                    ftod(budget_items[idx_budget][key]['values']['year'][p]['actual_value'] / calculate_month, 2)

    # Схлопнем годовую курсовую разницу
    try:
        ped_list = [POSITIVE_EXCHANGE_DIFFERENCE, Category.objects.get(pk=POSITIVE_EXCHANGE_DIFFERENCE).parent.pk, 0]
    except Exception as e:
        ped_list = [POSITIVE_EXCHANGE_DIFFERENCE, 0]
    try:
        ned_list = [NEGATIVE_EXCHANGE_DIFFERENCE, Category.objects.get(pk=NEGATIVE_EXCHANGE_DIFFERENCE).parent.pk, 0]
    except Exception as e:
        ned_list = [NEGATIVE_EXCHANGE_DIFFERENCE, 0]

    if budget_items['income_items'].get(POSITIVE_EXCHANGE_DIFFERENCE):
        ped_actual_value = \
            budget_items['income_items'][POSITIVE_EXCHANGE_DIFFERENCE]['values']['year']['all']['actual_value']
    else:
        ped_actual_value = ftod(0.00, 2)

    if budget_items['expenditure_items'].get(NEGATIVE_EXCHANGE_DIFFERENCE):
        ned_actual_value = \
            budget_items['expenditure_items'][NEGATIVE_EXCHANGE_DIFFERENCE]['values']['year']['all']['actual_value']
    else:
        ned_actual_value = ftod(0.00, 2)

    dif = ftod(ned_actual_value, 2) if ped_actual_value >= ned_actual_value else ftod(ped_actual_value, 2)

    if budget_items['income_items'].get(POSITIVE_EXCHANGE_DIFFERENCE):
        for c in ped_list:
            for p in ['all', 'non_project']:
                budget_items['income_items'][c]['values']['year'][p]['actual_value'] -= dif
                budget_items['income_items'][c]['values']['year'][p]['execution_percentage'] = \
                    get_execution_percentage(budget_items['income_items'][c]['values']['year'][p]['current_plan'],
                                             budget_items['income_items'][c]['values']['year'][p]['actual_value'])
                budget_items['income_items'][c]['values']['year'][p]['average_value'] = \
                    ftod(budget_items['income_items'][c]['values']['year'][p]['actual_value'] / calculate_month, 2)
    else:
        for p in ['all', 'non_project']:
            budget_items['income_items'][0]['values']['year'][p]['actual_value'] -= dif
            budget_items['income_items'][0]['values']['year'][p]['execution_percentage'] = \
                get_execution_percentage(budget_items['income_items'][0]['values']['year'][p]['current_plan'],
                                         budget_items['income_items'][0]['values']['year'][p]['actual_value'])
            budget_items['income_items'][0]['values']['year'][p]['average_value'] = \
                ftod(budget_items['income_items'][0]['values']['year'][p]['actual_value'] / calculate_month, 2)

    if budget_items['expenditure_items'].get(NEGATIVE_EXCHANGE_DIFFERENCE):
        for c in ned_list:
            for p in ['all', 'non_project']:
                budget_items['expenditure_items'][c]['values']['year'][p]['actual_value'] -= dif
                budget_items['expenditure_items'][c]['values']['year'][p]['execution_percentage'] = \
                    get_execution_percentage(budget_items['expenditure_items'][c]['values']['year'][p]['current_plan'],
                                             budget_items['expenditure_items'][c]['values']['year'][p]['actual_value'])
                budget_items['expenditure_items'][c]['values']['year'][p]['average_value'] = \
                    ftod(budget_items['expenditure_items'][c]['values']['year'][p]['actual_value'] / calculate_month, 2)
    else:
        for p in ['all', 'non_project']:
            budget_items['expenditure_items'][0]['values']['year'][p]['actual_value'] -= dif
            budget_items['expenditure_items'][0]['values']['year'][p]['execution_percentage'] = \
                get_execution_percentage(budget_items['expenditure_items'][0]['values']['year'][p]['current_plan'],
                                         budget_items['expenditure_items'][0]['values']['year'][p]['actual_value'])
            budget_items['expenditure_items'][0]['values']['year'][p]['average_value'] = \
                ftod(budget_items['expenditure_items'][0]['values']['year'][p]['actual_value'] / calculate_month, 2)

    # Посчитаем раздел 5 Сальдо
    for m in range(1, 13):
        for p in ['all', 'project', 'non_project']:
            budget_items['difference']['values'][m][p]['planned_value'] = \
                budget_items['income_items'][0]['values'][m][p]['planned_value'] - \
                budget_items['expenditure_items'][0]['values'][m][p]['planned_value']
            budget_items['difference']['values'][m][p]['actual_value'] = \
                budget_items['income_items'][0]['values'][m][p]['actual_value'] - \
                budget_items['expenditure_items'][0]['values'][m][p]['actual_value']
            budget_items['difference']['values'][m][p]['execution_percentage'] = \
                get_execution_percentage(budget_items['difference']['values'][m][p]['planned_value'],
                                         budget_items['difference']['values'][m][p]['actual_value'])

    for p in ['all', 'project', 'non_project']:
        budget_items['difference']['values']['year'][p]['planned_value'] = \
            budget_items['income_items'][0]['values']['year'][p]['planned_value'] - \
            budget_items['expenditure_items'][0]['values']['year'][p]['planned_value']
        budget_items['difference']['values']['year'][p]['actual_value'] = \
            budget_items['income_items'][0]['values']['year'][p]['actual_value'] - \
            budget_items['expenditure_items'][0]['values']['year'][p]['actual_value']
        budget_items['difference']['values']['year'][p]['current_plan'] = \
            budget_items['income_items'][0]['values']['year'][p]['current_plan'] - \
            budget_items['expenditure_items'][0]['values']['year'][p]['current_plan']
        budget_items['difference']['values']['year'][p]['execution_percentage'] = \
            get_execution_percentage(budget_items['difference']['values']['year'][p]['current_plan'],
                                     budget_items['difference']['values']['year'][p]['actual_value'])
        budget_items['difference']['values']['year'][p]['average_value'] = \
            ftod(budget_items['difference']['values']['year'][p]['actual_value'] / calculate_month, 2)

    # Посчитаем разделы 1 и 4 Остатки на начало и конец - фактические остатки
    accounts = Account.objects.filter(budget_id=budget_id).order_by('name')
    for account in accounts:
        parent_id = budget_items['opening_balance'][account.id]['parent_id']
        parent_parent_id = budget_items['opening_balance'][account.id]['parent_parent_id']
        for m in range(1, 14):
            # Определяем дату получения остатка
            on_date = datetime(year, m, 1, 0, 0, 0, 0, timezone.utc) if m != 13 \
                else datetime(year + 1, 1, 1, 0, 0, 0, 0, timezone.utc)

            # Получаем кортеж остатков
            balance_base_cur_1, balance_base_cur_2 = account.get_budget_balance_on_date(on_date)

            # Берем остаток нужной валюты
            actual_balance = ftod(balance_base_cur_1, 2) if currency_id == budget_base_currency_1 \
                else ftod(balance_base_cur_2, 2)

            # Снесем флаг незаполненности, если остаток не пуст
            if actual_balance:
                budget_items['opening_balance'][account.id]['is_empty'] = False
                budget_items['opening_balance'][parent_id]['is_empty'] = False
                budget_items['opening_balance'][parent_parent_id]['is_empty'] = False
                budget_items['closing_balance'][account.id]['is_empty'] = False
                budget_items['closing_balance'][parent_id]['is_empty'] = False
                budget_items['closing_balance'][parent_parent_id]['is_empty'] = False

            # Сохраняем в массив
            if m != 13:
                budget_items['opening_balance'][account.id]['values'][m]['actual_balance'] = ftod(actual_balance, 2)
                budget_items['opening_balance'][parent_id]['values'][m]['actual_balance'] += ftod(actual_balance, 2)
                budget_items['opening_balance'][parent_parent_id]['values'][m]['actual_balance'] += \
                    ftod(actual_balance, 2)
                budget_items['opening_balance'][0]['values'][m]['actual_balance'] += ftod(actual_balance, 2)
            if m != 1:
                budget_items['closing_balance'][account.id]['values'][m - 1]['actual_balance'] = ftod(actual_balance, 2)
                budget_items['closing_balance'][parent_id]['values'][m - 1]['actual_balance'] += ftod(actual_balance, 2)
                budget_items['closing_balance'][parent_parent_id]['values'][m - 1]['actual_balance'] += \
                    ftod(actual_balance, 2)
                budget_items['closing_balance'][0]['values'][m - 1]['actual_balance'] += ftod(actual_balance, 2)

        # Заполним остатки на начало года
        budget_items['opening_balance'][account.id]['values']['year']['actual_balance'] = \
            budget_items['opening_balance'][account.id]['values'][1]['actual_balance']
        budget_items['opening_balance'][parent_id]['values']['year']['actual_balance'] = \
            budget_items['opening_balance'][parent_id]['values'][1]['actual_balance']
        budget_items['opening_balance'][parent_parent_id]['values']['year']['actual_balance'] = \
            budget_items['opening_balance'][parent_parent_id]['values'][1]['actual_balance']
        budget_items['opening_balance'][0]['values']['year']['actual_balance'] = \
            budget_items['opening_balance'][0]['values'][1]['actual_balance']

        # Заполним остатки на конец года
        budget_items['closing_balance'][account.id]['values']['year']['actual_balance'] = \
            budget_items['closing_balance'][account.id]['values'][12]['actual_balance']
        budget_items['closing_balance'][parent_id]['values']['year']['actual_balance'] = \
            budget_items['closing_balance'][parent_id]['values'][12]['actual_balance']
        budget_items['closing_balance'][parent_parent_id]['values']['year']['actual_balance'] = \
            budget_items['closing_balance'][parent_parent_id]['values'][12]['actual_balance']
        budget_items['closing_balance'][0]['values']['year']['actual_balance'] = \
            budget_items['closing_balance'][0]['values'][12]['actual_balance']

    digit_rounding = request.user.profile.budget.digit_rounding
    # Посчитаем разделы 1 и 4 Остатки на начало и конец - Плановые остатки
    for m in range(1, 13):
        if m == 1:
            budget_items['opening_balance'][0]['values'][1]['planned_balance'] = \
                balance_round(budget_items['opening_balance'][0]['values'][1]['actual_balance'], digit_rounding)
        else:
            budget_items['opening_balance'][0]['values'][m]['planned_balance'] = \
                budget_items['closing_balance'][0]['values'][m - 1]['planned_balance']
        budget_items['closing_balance'][0]['values'][m]['planned_balance'] = \
            budget_items['opening_balance'][0]['values'][m]['planned_balance'] + \
            budget_items['difference']['values'][m]['all']['planned_value']

    # Заполним остаток на начало года
    budget_items['opening_balance'][0]['values']['year']['planned_balance'] = \
        budget_items['opening_balance'][0]['values'][1]['planned_balance']
    budget_items['opening_balance'][0]['values']['year']['current_plan'] = \
        budget_items['opening_balance'][0]['values'][1]['planned_balance']

    # Заполним остаток на конец года
    budget_items['closing_balance'][0]['values']['year']['planned_balance'] = \
        budget_items['closing_balance'][0]['values'][12]['planned_balance']
    budget_items['closing_balance'][0]['values']['year']['current_plan'] = \
        budget_items['closing_balance'][0]['values'][calculate_month]['planned_balance']
    budget_items['closing_balance'][0]['values']['year']['execution_percentage'] = \
        get_execution_percentage(budget_items['closing_balance'][0]['values']['year']['current_plan'],
                                 budget_items['closing_balance'][0]['values']['year']['actual_balance'])
    sum_actual_balance = ftod(0.00, 2)
    for m in range(1, calculate_month + 1):
        sum_actual_balance += ftod(budget_items['closing_balance'][0]['values'][m]['actual_balance'], 2)
    budget_items['closing_balance'][0]['values']['year']['average_balance'] = \
        ftod(sum_actual_balance / calculate_month, 2)

    # Снесем категории и счета/кошельки с пустыми балансами
    for key in list(budget_items['opening_balance'].keys()):
        if budget_items['opening_balance'][key]['is_empty']:
            budget_items['opening_balance'].pop(key, None)
    for key in list(budget_items['closing_balance'].keys()):
        if budget_items['closing_balance'][key]['is_empty']:
            budget_items['closing_balance'].pop(key, None)

    try:
        currency_iso_code = Currency.objects.get(pk=currency_id).iso_code
    except Exception as e:
        currency_iso_code = ''

    now = datetime.utcnow()
    end_budget_month = request.user.profile.budget.end_budget_month
    is_plan_editable = \
        request.user.profile.budget.user == request.user and \
        currency_id == budget_base_currency_1 and \
        (end_budget_month == 0 or now.year < year or (now.year == year and now.month <= end_budget_month))

    number_step = str(10 ** -digit_rounding).replace(',', '.')

    return render(request, 'main/budget_annual.html',
                  get_u_context(request, {'title': str(request.user.profile.budget) + ' ' + str(year) + ' г. в ' +
                                                   currency_iso_code,
                                          'budget_items': budget_items,
                                          'budget_id': request.user.profile.budget.id,
                                          'calculate_month': calculate_month,
                                          'ped_cat': POSITIVE_EXCHANGE_DIFFERENCE,
                                          'ned_cat': NEGATIVE_EXCHANGE_DIFFERENCE,
                                          'work_menu': True,
                                          'selected_menu': 'annual_budget',
                                          'budget_year_selected': year,
                                          'base_currency_selected': currency_id,
                                          'is_plan_editable': is_plan_editable,
                                          'number_step': number_step,
                                          'digit_rounding': digit_rounding,
                                          'dir_dict': {2: 'inc', 3: 'exp'}
                                          }))


@login_required
def edit_budget_register(request):
    """
    Функция изменения планового значения бюджетного регистра.
    Вызывается в асинхронном режиме с фронта AJAX
    """
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'PermissionDenied'}, status=403)
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return JsonResponse({'status': 'PermissionDenied'}, status=403)

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if is_ajax:
        if request.method == 'POST':
            planned_data = json.load(request)
            try:
                cat_budget_id = int(planned_data.get('cat_budget_id'))
                cat_year = int(planned_data.get('cat_year'))
                cat_month = int(planned_data.get('cat_month'))
                cat_id = int(planned_data.get('cat_id'))
                cat_parent_id = int(planned_data.get('cat_parent_id'))
                cat_dir = planned_data.get('cat_dir')
                cat_type = planned_data.get('cat_type')
                cat_planned_value = ftod(planned_data.get('cat_planned_value'), 2)
                if cat_dir == 'exp':
                    cat_planned_value = -cat_planned_value
            except Exception as e:
                return JsonResponse({'status': 'Error', 'error_massage': str(e)}, status=400)

            if int(planned_data.get('cat_budget_id')) != request.user.profile.budget.pk:
                return JsonResponse({'status': 'PermissionDenied'}, status=403)

            try:
                with transaction.atomic():
                    date_rate = date(cat_year, 1, 1) - timedelta(days=1)
                    rate = CurrencyRate.get_rate(request.user.profile.budget.base_currency_2_id,
                                                 request.user.profile.budget.base_currency_1_id,
                                                 date_rate)

                    budget_register_non_project, created = \
                        BudgetRegister.objects.get_or_create(budget_id=cat_budget_id,
                                                             budget_year=cat_year,
                                                             budget_month=cat_month,
                                                             category_id=cat_id,
                                                             project_id__isnull=True)
                    old_non_project = ftod(budget_register_non_project.planned_amount_base_cur_1, 2)

                    budget_register_project, created = \
                        BudgetRegister.objects.get_or_create(budget_id=cat_budget_id,
                                                             budget_year=cat_year,
                                                             budget_month=cat_month,
                                                             category_id=cat_id,
                                                             project_id=0)
                    old_project = ftod(budget_register_project.planned_amount_base_cur_1, 2)

                    old_all = ftod(old_non_project + old_project, 2)

                    new_non_project = ftod(old_non_project, 2)
                    new_project = ftod(old_project, 2)

                    if cat_type == 'all':
                        delta = cat_planned_value - ftod(old_non_project + old_project, 2)
                        delta_x = max(-old_non_project, delta) if cat_dir == 'inc' else -max(old_non_project, -delta)
                        delta_y = delta - delta_x

                        budget_register_non_project.planned_amount_base_cur_1 = \
                            ftod(budget_register_non_project.planned_amount_base_cur_1, 2) + ftod(delta_x, 2)
                        budget_register_non_project.planned_amount_base_cur_2 = \
                            ftod(budget_register_non_project.planned_amount_base_cur_1 * rate, 2)
                        budget_register_non_project.save()
                        new_non_project = ftod(budget_register_non_project.planned_amount_base_cur_1, 2)
                        if ftod(delta_y, 2) != ftod(0.00, 2):
                            budget_register_project.planned_amount_base_cur_1 = \
                                ftod(budget_register_project.planned_amount_base_cur_1, 2) + ftod(delta_y, 2)
                            budget_register_project.planned_amount_base_cur_2 = \
                                ftod(budget_register_project.planned_amount_base_cur_1 * rate, 2)
                            budget_register_project.save()
                            new_project = ftod(budget_register_project.planned_amount_base_cur_1, 2)

                    elif cat_type == 'non-project':
                        budget_register_non_project.planned_amount_base_cur_1 = ftod(cat_planned_value, 2)
                        budget_register_non_project.planned_amount_base_cur_2 = \
                            ftod(budget_register_non_project.planned_amount_base_cur_1 * rate, 2)
                        budget_register_non_project.save()
                        new_non_project = ftod(budget_register_non_project.planned_amount_base_cur_1, 2)

                    elif cat_type == 'project':
                        budget_register_project.planned_amount_base_cur_1 = ftod(cat_planned_value, 2)
                        budget_register_project.planned_amount_base_cur_2 = \
                            ftod(budget_register_project.planned_amount_base_cur_1 * rate, 2)
                        budget_register_project.save()
                        new_project = ftod(budget_register_project.planned_amount_base_cur_1, 2)

                    new_all = ftod(new_non_project + new_project, 2)

                    delta_all = ftod(new_all - old_all, 2)
                    delta_non_project = ftod(new_non_project - old_non_project, 2)
                    delta_project = ftod(new_project - old_project, 2)

                    if cat_dir == 'exp':
                        new_all = -new_all
                        new_non_project = -new_non_project
                        new_project = -new_project
                        delta_all = -delta_all
                        delta_non_project = -delta_non_project
                        delta_project = -delta_project

            except Exception as e:
                return JsonResponse({'status': 'Error', 'error_massage': str(e)}, status=400)

            return JsonResponse({'status': 'Ok',
                                 'new_all': new_all,
                                 'new_non_project': new_non_project,
                                 'new_project': new_project,
                                 'delta_all': delta_all,
                                 'delta_non_project': delta_non_project,
                                 'delta_project': delta_project,
                                 })

        return JsonResponse({'status': 'Invalid request'}, status=400)
    else:
        return JsonResponse({'status': 'Invalid request'}, status=400)


@login_required
def autoplanning_budget(request, budget_id, budget_year, return_url):
    """
    Функция автопланирования бюджета
    Доступны четыре функции:
    - Заполнить план января средним фактом предыдущего года;
    - Скопировать план января на все месяцы года;
    - Заполнить план всех месяцев средним фактом предыдущего года;
    - Удалить план.
    Предусмотрена опция - Типы значений для планирования:
    - Только текущие доходы и расходы;
    - Только проектные доходы и расходы;
    - И текущие, и проектные доходы и расходы.
    Также предусмотрена еще одна опция - Очистка текущих значений:
    - Предварительно удалить плановые значения;
    - Перезаписать только те плановые значения, которые есть в факте предыдущего года.
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    if budget_id != request.user.profile.budget.pk:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")
    if request.user.profile.budget.user != request.user:
        return HttpResponseForbidden("<h1>Доступ запрещен</h1>")

    if return_url[0:1] != '/':
        return_url = '/' + return_url

    # Проверка на попадание в период планирования бюджета
    now = datetime.utcnow()
    start_budget_month = request.user.profile.budget.start_budget_month
    end_budget_month = request.user.profile.budget.end_budget_month
    giving_year = budget_year - 1
    is_plan_editable = \
        end_budget_month == 0 or \
        now.year < budget_year or \
        (now.year == budget_year and now.month <= end_budget_month) or \
        (now.year == giving_year and now.month >= start_budget_month)
    if not is_plan_editable:
        return redirect('home')

    # Определим количество месяцев для расчета средних значений факта
    months = 12 if now.year != giving_year else now.month

    if request.method == 'POST':
        form = AutoplanningBudgetForm(data=request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Заполняем план из факта предыдущего года
                    if request.POST['plan_action'] in ['fill_january', 'fill_all_month']:

                        # Удалим сначала существующий план, при наличии указания на сие
                        if request.POST['clean_needed'] == 'delete_first':
                            if request.POST['plan_action'] == 'fill_january' and \
                                    request.POST['types_for_planning'] == 'only_current':
                                (BudgetRegister.objects
                                 .filter(budget_id=budget_id, budget_year=budget_year,
                                         budget_month=1, project_id__isnull=True)
                                 .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                         planned_amount_base_cur_2=ftod(0.00, 2))
                                 )
                            elif request.POST['plan_action'] == 'fill_january' and \
                                    request.POST['types_for_planning'] == 'only_project':
                                (BudgetRegister.objects
                                 .filter(budget_id=budget_id, budget_year=budget_year,
                                         budget_month=1, project_id__isnull=False)
                                 .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                         planned_amount_base_cur_2=ftod(0.00, 2))
                                 )
                            elif request.POST['plan_action'] == 'fill_january' and \
                                    request.POST['types_for_planning'] == 'both':
                                (BudgetRegister.objects
                                 .filter(budget_id=budget_id, budget_year=budget_year,
                                         budget_month=1)
                                 .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                         planned_amount_base_cur_2=ftod(0.00, 2))
                                 )
                            elif request.POST['plan_action'] == 'fill_all_month' and \
                                    request.POST['types_for_planning'] == 'only_current':
                                (BudgetRegister.objects
                                 .filter(budget_id=budget_id, budget_year=budget_year,
                                         project_id__isnull=True)
                                 .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                         planned_amount_base_cur_2=ftod(0.00, 2))
                                 )
                            elif request.POST['plan_action'] == 'fill_all_month' and \
                                    request.POST['types_for_planning'] == 'only_project':
                                (BudgetRegister.objects
                                 .filter(budget_id=budget_id, budget_year=budget_year,
                                         project_id__isnull=False)
                                 .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                         planned_amount_base_cur_2=ftod(0.00, 2))
                                 )
                            elif request.POST['plan_action'] == 'fill_all_month' and \
                                    request.POST['types_for_planning'] == 'both':
                                (BudgetRegister.objects
                                 .filter(budget_id=budget_id, budget_year=budget_year)
                                 .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                         planned_amount_base_cur_2=ftod(0.00, 2))
                                 )

                        # Возьмем курс для дополнительной валюты на начало планируемого года
                        rate = CurrencyRate.get_rate(request.user.profile.budget.base_currency_2_id,
                                                     request.user.profile.budget.base_currency_1_id,
                                                     date(budget_year, 1, 1) - timedelta(days=1))

                        # Будем изменять только январь или весь год в зависимости от выбора пользователя
                        if request.POST['plan_action'] == 'fill_january':
                            month_range = range(1, 2)
                        else:
                            month_range = range(1, 13)

                        digit_rounding = request.user.profile.budget.digit_rounding

                        # Заполнение плана для текущих доходов и расходов
                        if request.POST['types_for_planning'] in ['only_current', 'both']:
                            # Возьмем бюджетные регистры за предыдущий год кроме курсовых разниц
                            actual_current_values = (BudgetRegister.objects
                                                     .values('category_id')
                                                     .annotate(actual_sum=Sum('actual_amount_base_cur_1'))
                                                     .filter(budget_id=budget_id, budget_year=giving_year,
                                                             project_id__isnull=True)
                                                     .values('category_id', 'actual_sum'))

                            for actual_current_value in actual_current_values:
                                if actual_current_value.get('category_id') not in [POSITIVE_EXCHANGE_DIFFERENCE,
                                                                                   NEGATIVE_EXCHANGE_DIFFERENCE]:
                                    # Считаем среднее для базовой валюты
                                    ac_val_1 = \
                                        balance_round(actual_current_value.get('actual_sum', 0) / months,
                                                      digit_rounding)
                                    if ac_val_1 != ftod(0.00, 2):
                                        # Считаем среднее для дополнительной валюты
                                        ac_val_2 = ftod(ac_val_1 * rate, 2)
                                        # Записываем плановые значения в бюджетные регистры планируемого года
                                        # Если регистра нет, то создаем
                                        for month in month_range:
                                            br, created = \
                                                (BudgetRegister.objects
                                                 .get_or_create(budget_id=budget_id,
                                                                budget_year=budget_year,
                                                                budget_month=month,
                                                                category_id=actual_current_value.get('category_id'),
                                                                project_id__isnull=True)
                                                 )
                                            br.planned_amount_base_cur_1 = ac_val_1
                                            br.planned_amount_base_cur_2 = ac_val_2
                                            br.save()

                        # Заполнение плана для проектных доходов и расходов
                        if request.POST['types_for_planning'] in ['only_project', 'both']:
                            # Возьмем бюджетные регистры за предыдущий год кроме курсовых разниц
                            actual_project_values = (BudgetRegister.objects
                                                     .values('category_id')
                                                     .annotate(actual_sum=Sum('actual_amount_base_cur_1'))
                                                     .filter(budget_id=budget_id, budget_year=giving_year,
                                                             project_id__isnull=False)
                                                     .values('category_id', 'actual_sum'))
                            for actual_project_value in actual_project_values:
                                if actual_current_value.get('category_id') not in [POSITIVE_EXCHANGE_DIFFERENCE,
                                                                                   NEGATIVE_EXCHANGE_DIFFERENCE]:
                                    # Считаем среднее для базовой валюты
                                    ac_val_1 = \
                                        balance_round(actual_project_value.get('actual_sum', 0) / months, digit_rounding)
                                    if ac_val_1 != ftod(0.00, 2):
                                        # Считаем среднее для дополнительной валюты
                                        ac_val_2 = ftod(ac_val_1 * rate, 2)
                                        # Записываем плановые значения в бюджетные регистры планируемого года
                                        # Если регистра нет, то создаем
                                        for month in month_range:
                                            br, created = \
                                                (BudgetRegister.objects
                                                 .get_or_create(budget_id=budget_id,
                                                                budget_year=budget_year,
                                                                budget_month=month,
                                                                category_id=actual_project_value.get('category_id'),
                                                                project_id=0)
                                                 )
                                            br.planned_amount_base_cur_1 = ac_val_1
                                            br.planned_amount_base_cur_2 = ac_val_2
                                            br.save()

                    # Копируем план января во все месяцы года
                    elif request.POST['plan_action'] == 'copy_january_to_all_month':

                        # Удалим сначала существующий план, при наличии указания на сие
                        if request.POST['clean_needed'] == 'delete_first':
                            if request.POST['types_for_planning'] == 'only_current':
                                (BudgetRegister.objects
                                 .filter(budget_id=budget_id, budget_year=budget_year,
                                         budget_month__gt=1, project_id__isnull=True)
                                 .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                         planned_amount_base_cur_2=ftod(0.00, 2))
                                 )
                            elif request.POST['types_for_planning'] == 'only_project':
                                (BudgetRegister.objects
                                 .filter(budget_id=budget_id, budget_year=budget_year,
                                         budget_month__gt=1, project_id__isnull=False)
                                 .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                         planned_amount_base_cur_2=ftod(0.00, 2))
                                 )
                            elif request.POST['types_for_planning'] == 'both':
                                (BudgetRegister.objects
                                 .filter(budget_id=budget_id, budget_year=budget_year,
                                         budget_month__gt=1)
                                 .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                         planned_amount_base_cur_2=ftod(0.00, 2))
                                 )

                        # Берем плановые значения января (различные опции)
                        if request.POST['types_for_planning'] == 'only_current':
                            planned_values = BudgetRegister.objects.filter(budget_id=budget_id,
                                                                           budget_year=budget_year,
                                                                           budget_month=1,
                                                                           project_id__isnull=True)
                        elif request.POST['types_for_planning'] == 'only_project':
                            planned_values = BudgetRegister.objects.filter(budget_id=budget_id,
                                                                           budget_year=budget_year,
                                                                           budget_month=1,
                                                                           project_id=0)
                        else:
                            planned_values = BudgetRegister.objects.filter(budget_id=budget_id,
                                                                           budget_year=budget_year,
                                                                           budget_month=1)
                        for planned_value in planned_values:
                            if planned_value.category_id not in [POSITIVE_EXCHANGE_DIFFERENCE,
                                                                 NEGATIVE_EXCHANGE_DIFFERENCE]:
                                ac_val_1 = ftod(planned_value.planned_amount_base_cur_1, 2)
                                if ac_val_1 != ftod(0.00, 2):
                                    ac_val_2 = ftod(planned_value.planned_amount_base_cur_2, 2)
                                    # Записываем плановые значения в бюджетные регистры планируемого года
                                    # Если регистра нет, то создаем
                                    for month in range(2, 13):
                                        if planned_value.project_id is None:
                                            br, created = \
                                                (BudgetRegister.objects
                                                 .get_or_create(budget_id=budget_id,
                                                                budget_year=budget_year,
                                                                budget_month=month,
                                                                category_id=planned_value.category_id,
                                                                project_id__isnull=True)
                                                 )
                                            br.planned_amount_base_cur_1 = ac_val_1
                                            br.planned_amount_base_cur_2 = ac_val_2
                                            br.save()
                                        else:
                                            br, created = \
                                                (BudgetRegister.objects
                                                 .get_or_create(budget_id=budget_id,
                                                                budget_year=budget_year,
                                                                budget_month=month,
                                                                category_id=planned_value.category_id,
                                                                project_id=0)
                                                 )
                                            br.planned_amount_base_cur_1 = ac_val_1
                                            br.planned_amount_base_cur_2 = ac_val_2
                                            br.save()

                    # Удаляем план
                    elif request.POST['plan_action'] == 'delete':
                        if request.POST['types_for_planning'] == 'only_current':
                            (BudgetRegister.objects
                             .filter(budget_id=budget_id, budget_year=budget_year,
                                     project_id__isnull=True)
                             .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                     planned_amount_base_cur_2=ftod(0.00, 2))
                             )
                        elif request.POST['types_for_planning'] == 'only_project':
                            (BudgetRegister.objects
                             .filter(budget_id=budget_id, budget_year=budget_year,
                                     project_id__isnull=False)
                             .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                     planned_amount_base_cur_2=ftod(0.00, 2))
                             )
                        elif request.POST['types_for_planning'] == 'both':
                            (BudgetRegister.objects
                             .filter(budget_id=budget_id, budget_year=budget_year)
                             .update(planned_amount_base_cur_1=ftod(0.00, 2),
                                     planned_amount_base_cur_2=ftod(0.00, 2))
                             )

                return redirect(return_url)

            except Exception as e:
                form.add_error(None, 'Ошибка автопланирования бюджета: ' + str(e))

    else:
        form = AutoplanningBudgetForm()
    return render(request, 'main/budget_autoplanning.html',
                  get_u_context(request, {'title': 'Автоматическое заполнение плана',
                                          'budget_year': budget_year,
                                          'giving_year': giving_year,
                                          'form': form,
                                          'return_url': return_url,
                                          'work_menu': True,
                                          'selected_menu': 'annual_budget',
                                          'budget_year_selected': budget_year,
                                          'base_currency_selected': DEFAULT_BASE_CURRENCY_1,
                                          })
                  )


@login_required
def current_state(request, currency_id, month_shift):
    """
    Функция просмотра текущего состояния.
    Показывает фактические остатки на счетах в разрезе валют и групп типов счетов/кошельков.
    Показывает факт текущего месяца, план текущего месяца и его исполнение.
    Также показывает факт предыдущих 12 месяцев и их среднее.
    Для каждого фактического значения категорий второго уровня предусмотрена возможность
    просмотреть список операций его составляющих.
    Сделана возможность посмотреть текущее состояние не только на текущий месяц,
    но и на месяц и более ранее (month_shift > 0)
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    else:
        budget_id = request.user.profile.budget_id

    expanded_category_id = int(request.GET.get("cat_id", -1))

    budget_base_currency_1 = request.user.profile.budget.base_currency_1_id

    # Создаем массив из 13 месяцев (текущий - month_shift и 12 предыдущих)
    months = []
    d = datetime.utcnow()
    d = datetime(d.year, d.month, 1, 0, 0, 0, 0, timezone.utc)
    for m in range(month_shift):
        d = d - timedelta(days=1)
        d = datetime(d.year, d.month, 1, 0, 0, 0, 0, timezone.utc)
    if month_shift == 0:
        month_name = 'текущий '
    elif month_shift == 1:
        month_name = 'предыдущий '
    else:
        month_name = ''
    month_name = month_name + str(d.year).zfill(4) + ' ' + str(d.month).zfill(2)
    for m in range(13):
        months.append((d.year, d.month))
        d = d - timedelta(days=1)
        d = datetime(d.year, d.month, 1, 0, 0, 0, 0, timezone.utc)

    d = datetime(months[0][0], months[0][1], 28, 0, 0, 0, 0, timezone.utc) + timedelta(days=4)
    months.reverse()
    m_extra = (d.year, d.month)
    months_extra = months.copy()
    months_extra.append(m_extra)

    # Это результирующий словарь бюджета
    budget_items = dict()

    # Добавляем пустой раздел 1 "Остатки на начало"
    budget_items['opening_balance'] = \
        {0: {'item': '1.',
             'name': 'ОСТАТКИ НА НАЧАЛО',
             'parent_parent_id': 0,
             'parent_id': 0,
             'is_empty': False,
             'values': {m: {'actual_balance': ftod(0.00, 2)}
                        for m in months}
             }
         }
    budget_items['opening_balance'][0]['values']['summary'] = \
        {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
         'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}

    # Добавляем категории счетов/кошельков из константы ACCOUNT_TYPES и сами счета/кошельки
    n_type_category = 1
    for account_type_category in ACCOUNT_TYPES[1:]:
        budget_items['opening_balance'][account_type_category[0]] = \
            {'item': '1.' + str(n_type_category) + '.',
             'name': account_type_category[0],
             'parent_parent_id': 0,
             'parent_id': 0,
             'is_empty': True,
             'values': {m: {'actual_balance': ftod(0.00, 2)}
                        for m in months}
             }
        budget_items['opening_balance'][account_type_category[0]]['values']['summary'] = \
            {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
             'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
        n_type = 1
        for account_type in account_type_category[1]:
            budget_items['opening_balance'][account_type[0]] = \
                {'item': '1.' + str(n_type_category) + '.' + str(n_type) + '.',
                 'name': account_type[1],
                 'parent_parent_id': 0,
                 'parent_id': account_type_category[0],
                 'is_empty': True,
                 'values': {m: {'actual_balance': ftod(0.00, 2)}
                            for m in months}
                 }
            budget_items['opening_balance'][account_type[0]]['values']['summary'] = \
                {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                 'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
            accounts = Account.objects.filter(budget_id=budget_id, type=account_type[0]).order_by('name')
            n_account = 1
            for account in accounts:
                budget_items['opening_balance'][account.id] = \
                    {'item': '1.' + str(n_type_category) + '.' + str(n_type) + '.' + str(n_account) + '.',
                     'name': str(account),
                     'parent_parent_id': account_type_category[0],
                     'parent_id': account_type[0],
                     'is_empty': True,
                     'values': {m: {'actual_balance': ftod(0.00, 2)}
                                for m in months}
                     }
                budget_items['opening_balance'][account.id]['values']['summary'] = \
                    {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                     'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
                n_account += 1
            n_type += 1
        n_type_category += 1

    # Добавляем пустой раздел 2 "Доходы" (результирующая строка со столбцами по месяцам и году в целом)
    # Значения План/Факт/% исполнения представляется в трех разрезах: Общая сумма / Текущий приход / Проектный приход
    budget_items['income_items'] = \
        {0: {'item': '2.',
             'name': 'ДОХОДЫ',
             'parent_id': 0,
             'is_empty': False,
             'hidden_children': {},
             'values': {m: {p: {'actual_value': ftod(0.00, 2)
                                } for p in ['all', 'project', 'non_project']} for m in months}
             }
         }
    budget_items['income_items'][0]['values']['summary'] = \
        {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
             'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
             } for p in ['all', 'project', 'non_project']
         }

    # Дополняем раздел 2 "Доходы" категориями из справочника из базы данных
    for cat, dic in tree_item_iterator(Category.objects.filter(type='INC')):
        if not cat.budget or cat.budget.pk == budget_id:
            try:
                parent_id = cat.parent.id
            except Exception as e:
                parent_id = 0
            budget_items['income_items'][cat.id] = \
                {'item': '2.' + cat.item,
                 'name': cat.name,
                 'parent_id': parent_id,
                 'is_empty': True,
                 'hidden_children': {},
                 'values': {}
                 }

    # Добавляем пустой раздел 3 "Расходы" (результирующая строка со столбцами по месяцам и году в целом)
    # Значения План/Факт/% исполнения представляется в трех разрезах: Общая сумма / Текущий расход / Проектный расход
    budget_items['expenditure_items'] = \
        {0: {'item': '3.',
             'name': 'РАСХОДЫ',
             'parent_id': 0,
             'is_empty': False,
             'hidden_children': {},
             'values': {m: {p: {'actual_value': ftod(0.00, 2)
                                } for p in ['all', 'project', 'non_project']} for m in months}
             }
         }
    budget_items['expenditure_items'][0]['values']['summary'] = \
        {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
             'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
             } for p in ['all', 'project', 'non_project']
         }

    # Дополняем раздел 3 "Расходы" категориями из справочника из базы данных
    for cat, dic in tree_item_iterator(Category.objects.filter(type='EXP')):
        if not cat.budget or cat.budget.pk == budget_id:
            try:
                parent_id = cat.parent.id
            except Exception as e:
                parent_id = 0
            budget_items['expenditure_items'][cat.id] = \
                {'item': '3.' + cat.item,
                 'name': cat.name,
                 'parent_id': parent_id,
                 'is_empty': True,
                 'hidden_children': {},
                 'values': {}
                 }

    # Добавляем пустой раздел 4 "Остатки на конец"
    budget_items['closing_balance'] = \
        {0: {'item': '4.',
             'name': 'ОСТАТКИ НА КОНЕЦ',
             'parent_parent_id': 0,
             'parent_id': 0,
             'is_empty': False,
             'values': {m: {'actual_balance': ftod(0.00, 2)}
                        for m in months}
             }
         }
    budget_items['closing_balance'][0]['values']['summary'] = \
        {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
         'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}

    # Добавляем категории счетов/кошельков из константы ACCOUNT_TYPES и сами счета/кошельки
    n_type_category = 1
    for account_type_category in ACCOUNT_TYPES[1:]:
        budget_items['closing_balance'][account_type_category[0]] = \
            {'item': '4.' + str(n_type_category) + '.',
             'name': account_type_category[0],
             'parent_parent_id': 0,
             'parent_id': 0,
             'is_empty': True,
             'values': {m: {'actual_balance': ftod(0.00, 2)}
                        for m in months}
             }
        budget_items['closing_balance'][account_type_category[0]]['values']['summary'] = \
            {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
             'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
        n_type = 1
        for account_type in account_type_category[1]:
            budget_items['closing_balance'][account_type[0]] = \
                {'item': '4.' + str(n_type_category) + '.' + str(n_type) + '.',
                 'name': account_type[1],
                 'parent_parent_id': 0,
                 'parent_id': account_type_category[0],
                 'is_empty': True,
                 'values': {m: {'actual_balance': ftod(0.00, 2)}
                            for m in months}
                 }
            budget_items['closing_balance'][account_type[0]]['values']['summary'] = \
                {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                 'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
            accounts = Account.objects.filter(budget_id=budget_id, type=account_type[0]).order_by('name')
            n_account = 1
            for account in accounts:
                budget_items['closing_balance'][account.id] = \
                    {'item': '4.' + str(n_type_category) + '.' + str(n_type) + '.' + str(n_account) + '.',
                     'name': str(account),
                     'parent_parent_id': account_type_category[0],
                     'parent_id': account_type[0],
                     'is_empty': True,
                     'values': {m: {'actual_balance': ftod(0.00, 2)}
                                for m in months}
                     }
                budget_items['closing_balance'][account.id]['values']['summary'] = \
                    {'planned_balance': ftod(0.00, 2), 'actual_balance': ftod(0.00, 2),
                     'execution_percentage': ftod(0.0000, 4), 'average_balance': ftod(0.00, 2)}
                n_account += 1
            n_type += 1
        n_type_category += 1

    # Добавляем пустой раздел 5 "Сальдо" (одна результирующая строка со столбцами по месяцам и году в целом)
    budget_items['difference'] = \
        {'item': '5.',
         'name': 'САЛЬДО',
         'values': {m: {p: {'actual_value': ftod(0.00, 2)
                            } for p in ['all', 'project', 'non_project']} for m in months}
         }
    budget_items['difference']['values']['summary'] = \
        {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
             'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
             } for p in ['all', 'project', 'non_project']
         }

    # Вытаскиваем из базы данных для заданного бюджета регистры заданного года
    for year, month in months:
        budget_registers = (BudgetRegister.objects
                            .filter(budget_id=budget_id, budget_year=year, budget_month=month)
                            .select_related('category', 'project'))

        # Заполняем разделы 2 и 3 словаря данными из вытащенных регистров
        for budget_register in budget_registers:
            # Определяем приход или расход
            idx_budget = 'income_items' if budget_register.category.type == 'INC' else 'expenditure_items'

            # Определяем суммы исходя из валюты
            actual_value = ftod(budget_register.actual_amount_base_cur_1, 2) \
                if currency_id == budget_base_currency_1 \
                else ftod(budget_register.actual_amount_base_cur_2, 2)
            planned_value = ftod(budget_register.planned_amount_base_cur_1, 2) \
                if currency_id == budget_base_currency_1 \
                else ftod(budget_register.planned_amount_base_cur_2, 2)

            # Если суммы нулевые, то не будем добавлять строчку в массив, кроме курсовых разниц
            if budget_register.category_id not in [POSITIVE_EXCHANGE_DIFFERENCE, NEGATIVE_EXCHANGE_DIFFERENCE] and \
                    planned_value == ftod(0.00, 2) and actual_value == ftod(0.00, 2):
                continue

            # Для расходов снесем минуса для приятности глаз токмо
            if budget_register.category.type == 'EXP':
                actual_value = -actual_value
                planned_value = -planned_value

            category = budget_register.category_id
            parent_category = budget_register.category.parent_id
            project = budget_register.project

            # Проставим флаг заполненности категории
            budget_items[idx_budget][category]['is_empty'] = False
            budget_items[idx_budget][parent_category]['is_empty'] = False

            # Если по категории массив со значениями пустой, то задефолтим
            if not budget_items[idx_budget][category]['values']:
                budget_items[idx_budget][category]['values'] = \
                    {m: {p: {'actual_value': ftod(0.00, 2)
                             } for p in ['all', 'project', 'non_project']} for m in months}
                budget_items[idx_budget][category]['values']['summary'] = \
                    {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                         'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
                         } for p in ['all', 'project', 'non_project']
                     }

            # Если по родительской категории массив со значениями пустой, то задефолтим
            if not budget_items[idx_budget][parent_category]['values']:
                budget_items[idx_budget][parent_category]['values'] = \
                     {m: {p: {'actual_value': ftod(0.00, 2)
                              } for p in ['all', 'project', 'non_project']} for m in months}
                budget_items[idx_budget][parent_category]['values']['summary'] = \
                    {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                         'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
                         } for p in ['all', 'project', 'non_project']
                     }

            # Перебор по Регистрам /Категория (категория регистра, родительская категория, приход или расход в целом)
            for c in [category, parent_category, 0]:
                # Перебор по Регистрам /Месяц или Год (месяц регистра или год в целом)

                # Регистр /общая сумма
                budget_items[idx_budget][c]['values'][(year, month)]['all']['actual_value'] += actual_value
                if (year, month) == months[len(months) - 1]:
                    budget_items[idx_budget][c]['values']['summary']['all']['planned_value'] += planned_value
                else:
                    budget_items[idx_budget][c]['values']['summary']['all']['actual_value'] += actual_value

                # Регистр /текущие или проектные
                if project:
                    budget_items[idx_budget][c]['values'][(year, month)]['project']['actual_value'] += actual_value
                    if (year, month) == months[len(months) - 1]:
                        budget_items[idx_budget][c]['values']['summary']['project']['planned_value'] += planned_value
                    else:
                        budget_items[idx_budget][c]['values']['summary']['project']['actual_value'] += actual_value
                    if project.id:
                        if not budget_items[idx_budget][c]['values'][(year, month)].get('projects', None):
                            budget_items[idx_budget][c]['values'][(year, month)]['projects'] = {}
                        if not budget_items[idx_budget][c]['values'][(year, month)]['projects'].get(project.id, None):
                            budget_items[idx_budget][c]['values'][(year, month)]['projects'][project.id] = \
                                {'name': project.name, 'actual_value': actual_value}
                        else:
                            budget_items[idx_budget][c]['values'][(year, month)]['projects'][project.id]['actual_value'] += \
                                actual_value
                else:
                    budget_items[idx_budget][c]['values'][(year, month)]['non_project']['actual_value'] += actual_value
                    if (year, month) == months[len(months) - 1]:
                        budget_items[idx_budget][c]['values']['summary']['non_project']['planned_value'] += \
                            planned_value
                    else:
                        budget_items[idx_budget][c]['values']['summary']['non_project']['actual_value'] += actual_value

    # Снесем категории с пустыми массивами значений. Родительские категории не трогаем
    for idx_budget in ['income_items', 'expenditure_items']:
        for key in list(budget_items[idx_budget].keys()):
            if not budget_items[idx_budget][key]['values']:
                parent_category_id = budget_items[idx_budget][key]['parent_id']
                if parent_category_id:
                    budget_items[idx_budget].pop(key, None)
                else:
                    budget_items[idx_budget][key]['values'] = \
                        {m: {p: {'actual_value': ftod(0.00, 2)
                                 } for p in ['all', 'project', 'non_project']} for m in months}
                    budget_items[idx_budget][key]['values']['summary'] = \
                        {p: {'planned_value': ftod(0.00, 2), 'actual_value': ftod(0.00, 2),
                             'execution_percentage': ftod(0.0000, 4), 'average_value': ftod(0.00, 2)
                             } for p in ['all', 'project', 'non_project']
                         }

    # Посчитаем для разделов 2 и 3 исполнение последнего месяца и среднее месячное
    for idx_budget in ['income_items', 'expenditure_items']:
        for key in budget_items[idx_budget].keys():
            for p in ['all', 'project', 'non_project']:
                budget_items[idx_budget][key]['values']['summary'][p]['execution_percentage'] = \
                    get_execution_percentage(budget_items[idx_budget][key]['values']['summary'][p]['planned_value'],
                                             budget_items[idx_budget][key]['values'][months[len(months) - 1]][p]['actual_value'])
                budget_items[idx_budget][key]['values']['summary'][p]['average_value'] = \
                    ftod(budget_items[idx_budget][key]['values']['summary'][p]['actual_value'] / (len(months) - 1), 2)

    # Посчитаем раздел 5 Сальдо
    for m in months:
        for p in ['all', 'project', 'non_project']:
            budget_items['difference']['values'][m][p]['actual_value'] = \
                budget_items['income_items'][0]['values'][m][p]['actual_value'] - \
                budget_items['expenditure_items'][0]['values'][m][p]['actual_value']

    for p in ['all', 'project', 'non_project']:
        budget_items['difference']['values']['summary'][p]['planned_value'] = \
            budget_items['income_items'][0]['values']['summary'][p]['planned_value'] - \
            budget_items['expenditure_items'][0]['values']['summary'][p]['planned_value']
        budget_items['difference']['values']['summary'][p]['actual_value'] = \
            budget_items['income_items'][0]['values']['summary'][p]['actual_value'] - \
            budget_items['expenditure_items'][0]['values']['summary'][p]['actual_value']
        budget_items['difference']['values']['summary'][p]['execution_percentage'] = \
            get_execution_percentage(budget_items['difference']['values']['summary'][p]['planned_value'],
                                     budget_items['difference']['values']['summary'][p]['actual_value'])
        budget_items['difference']['values']['summary'][p]['average_value'] = \
            ftod(budget_items['difference']['values']['summary'][p]['actual_value'] / len(months) - 1, 2)

    # Посчитаем разделы 1 и 4 Остатки на начало и конец - фактические остатки
    accounts = Account.objects.filter(budget_id=budget_id).order_by('name')
    for account in accounts:
        parent_id = budget_items['opening_balance'][account.id]['parent_id']
        parent_parent_id = budget_items['opening_balance'][account.id]['parent_parent_id']

        m_prev = None
        for m in months_extra:
            # Определяем дату получения остатка
            on_date = datetime(m[0], m[1], 1, 0, 0, 0, 0, timezone.utc)

            # Получаем кортеж остатков
            balance_base_cur_1, balance_base_cur_2 = account.get_budget_balance_on_date(on_date)

            # Берем остаток нужной валюты
            actual_balance = ftod(balance_base_cur_1, 2) if currency_id == budget_base_currency_1 \
                else ftod(balance_base_cur_2, 2)

            # Снесем флаг незаполненности, если остаток не пуст
            if actual_balance:
                budget_items['opening_balance'][account.id]['is_empty'] = False
                budget_items['opening_balance'][parent_id]['is_empty'] = False
                budget_items['opening_balance'][parent_parent_id]['is_empty'] = False
                budget_items['closing_balance'][account.id]['is_empty'] = False
                budget_items['closing_balance'][parent_id]['is_empty'] = False
                budget_items['closing_balance'][parent_parent_id]['is_empty'] = False

            # Сохраняем в массив
            if m != months_extra[len(months_extra) - 1]:
                budget_items['opening_balance'][account.id]['values'][m]['actual_balance'] = \
                    ftod(actual_balance, 2)
                budget_items['opening_balance'][parent_id]['values'][m]['actual_balance'] += \
                    ftod(actual_balance, 2)
                budget_items['opening_balance'][parent_parent_id]['values'][m]['actual_balance'] += \
                    ftod(actual_balance, 2)
                budget_items['opening_balance'][0]['values'][m]['actual_balance'] += \
                    ftod(actual_balance, 2)
            if m_prev:
                budget_items['closing_balance'][account.id]['values'][m_prev]['actual_balance'] = \
                    ftod(actual_balance, 2)
                budget_items['closing_balance'][parent_id]['values'][m_prev]['actual_balance'] += \
                    ftod(actual_balance, 2)
                budget_items['closing_balance'][parent_parent_id]['values'][m_prev]['actual_balance'] += \
                    ftod(actual_balance, 2)
                budget_items['closing_balance'][0]['values'][m_prev]['actual_balance'] += \
                    ftod(actual_balance, 2)

            m_prev = m

    # Посчитаем разделы 1 и 4 Остатки на начало и конец - Плановые остатки
    # заполним остаток на начало последнего месяца
    budget_items['opening_balance'][0]['values']['summary']['planned_balance'] = \
        balance_round(budget_items['opening_balance'][0]['values'][months[len(months) - 1]]['actual_balance'],
                      request.user.profile.budget.digit_rounding)
    # заполним остаток на конец последнего месяца
    budget_items['closing_balance'][0]['values']['summary']['planned_balance'] = \
        budget_items['opening_balance'][0]['values']['summary']['planned_balance'] + \
        budget_items['difference']['values']['summary']['all']['planned_value']

    # Снесем категории и счета/кошельки с пустыми балансами
    for key in list(budget_items['opening_balance'].keys()):
        if budget_items['opening_balance'][key]['is_empty']:
            budget_items['opening_balance'].pop(key, None)
    for key in list(budget_items['closing_balance'].keys()):
        if budget_items['closing_balance'][key]['is_empty']:
            budget_items['closing_balance'].pop(key, None)

    try:
        currency_iso_code = Currency.objects.get(pk=currency_id).iso_code
    except Exception as e:
        currency_iso_code = ''

    # Вытащим остатки по счетам, сгруппированные по валютам и группам счетов
    balances_by_currencies = (Account.objects
                              .values('currency_id', 'group')
                              .annotate(balance_sum=Sum('balance'),
                                        credit_limit_sum=Sum('credit_limit'),
                                        balance_base_cur_1_sum=Sum('balance_base_cur_1'),
                                        balance_base_cur_2_sum=Sum('balance_base_cur_2'),
                                        )
                              .filter(budget_id=request.user.profile.budget.pk)
                              .values('currency_id', 'group', 'balance_sum', 'credit_limit_sum',
                                      'balance_base_cur_1_sum', 'balance_base_cur_2_sum')
                              .order_by('currency_id', 'group')
                              )

    # Итоговый массив остатков
    balance_items = {}

    # Заполним массив данными из выборки
    for balance_by_currencies in balances_by_currencies:
        if not balance_items.get(balance_by_currencies.get('currency_id')):
            currency = Currency.objects.get(pk=balance_by_currencies.get('currency_id'))
            balance_items[balance_by_currencies.get('currency_id')] = {
                'currency_name': str(currency),
                'currency_iso_code': currency.iso_code,
                'values': {
                    '1.CASH':
                        {'balance': ftod(0.00, 2), 'credit_limit': ftod(0.00, 2), 'balance_base_cur': ftod(0.00, 2)},
                    '2.CURR':
                        {'balance': ftod(0.00, 2), 'credit_limit': ftod(0.00, 2), 'balance_base_cur': ftod(0.00, 2)},
                    '3.CRED':
                        {'balance': ftod(0.00, 2), 'credit_limit': ftod(0.00, 2), 'balance_base_cur': ftod(0.00, 2)},
                    '4.DEBT':
                        {'balance': ftod(0.00, 2), 'credit_limit': ftod(0.00, 2), 'balance_base_cur': ftod(0.00, 2)},
                    '5.INVS':
                        {'balance': ftod(0.00, 2), 'credit_limit': ftod(0.00, 2), 'balance_base_cur': ftod(0.00, 2)},
                    '6.BUSN':
                        {'balance': ftod(0.00, 2), 'credit_limit': ftod(0.00, 2), 'balance_base_cur': ftod(0.00, 2)},
                    'TOTAL':
                        {'balance': ftod(0.00, 2), 'credit_limit': ftod(0.00, 2), 'total': ftod(0.00, 2),
                         'balance_base_cur': ftod(0.00, 2), 'credit_limit_base_cur': ftod(0.00, 2),
                         'total_base_cur': ftod(0.00, 2)},
                }
            }
        balance_items[balance_by_currencies.get('currency_id')]['values'][balance_by_currencies.get('group')]['balance'] += \
            balance_by_currencies.get('balance_sum')
        balance_items[balance_by_currencies.get('currency_id')]['values'][balance_by_currencies.get('group')]['credit_limit'] += \
            balance_by_currencies.get('credit_limit_sum')
        balance_items[balance_by_currencies.get('currency_id')]['values'][balance_by_currencies.get('group')]['balance_base_cur'] += \
            ftod(balance_by_currencies.get('balance_base_cur_1_sum'), 2) if currency_id == budget_base_currency_1 \
            else ftod(balance_by_currencies.get('balance_base_cur_2_sum'), 2)
        balance_items[balance_by_currencies.get('currency_id')]['values']['TOTAL']['balance'] += \
            balance_by_currencies.get('balance_sum')
        balance_items[balance_by_currencies.get('currency_id')]['values']['TOTAL']['credit_limit'] += \
            balance_by_currencies.get('credit_limit_sum')
        balance_items[balance_by_currencies.get('currency_id')]['values']['TOTAL']['balance_base_cur'] += \
            ftod(balance_by_currencies.get('balance_base_cur_1_sum'), 2) if currency_id == budget_base_currency_1 \
            else ftod(balance_by_currencies.get('balance_base_cur_2_sum'), 2)

    # Дозаполним итоги и три суммы
    balance_totals = {'balance_base_cur': ftod(0.00, 2), 'credit_limit_base_cur': ftod(0.00, 2),
                      'total_base_cur': ftod(0.00, 2)}
    for cur_id, cur_dict in balance_items.items():
        cur_dict['values']['TOTAL']['total'] = \
            ftod(cur_dict['values']['TOTAL']['balance'] +
                 cur_dict['values']['TOTAL']['credit_limit'], 2)
        cur_dict['values']['TOTAL']['credit_limit_base_cur'] = \
            ftod(cur_dict['values']['TOTAL']['credit_limit'] *
                 CurrencyRate.get_rate(cur_id, currency_id, datetime.utcnow()), 2)
        cur_dict['values']['TOTAL']['total_base_cur'] = \
            ftod(cur_dict['values']['TOTAL']['balance_base_cur'] +
                 cur_dict['values']['TOTAL']['credit_limit_base_cur'], 2)
        balance_totals['balance_base_cur'] += cur_dict['values']['TOTAL']['balance_base_cur']
        balance_totals['credit_limit_base_cur'] += cur_dict['values']['TOTAL']['credit_limit_base_cur']
        balance_totals['total_base_cur'] += cur_dict['values']['TOTAL']['total_base_cur']

    return render(request, 'main/budget_current_state.html',
                  get_u_context(request, {'title': 'Текущее состояние: ' + request.user.profile.budget.name +
                                                   ', месяц: ' + month_name + ' в ' + currency_iso_code,
                                          'budget_items': budget_items,
                                          'budget_id': budget_id,
                                          'balance_items': balance_items,
                                          'balance_totals': balance_totals,
                                          'currency_iso_code': currency_iso_code,
                                          'months': months,
                                          'ped_cat': POSITIVE_EXCHANGE_DIFFERENCE,
                                          'ned_cat': NEGATIVE_EXCHANGE_DIFFERENCE,
                                          'work_menu': True,
                                          'selected_menu': 'current_state',
                                          'base_currency_selected': currency_id,
                                          'month_shift_selected': month_shift,
                                          'expanded_category_id': expanded_category_id,
                                          'dir_dict': {2: 'inc', 3: 'exp'}
                                          }))


class AccountTransactionsInCategoryPeriod(LoginRequiredMixin, DataMixin, ListView):
    """
    Просмотр операций, лежащих в основе факта бюджета конкретных: года, месяца, категории
    """
    model = Transaction
    template_name = 'main/account_transactions_in_category_period.html'
    context_object_name = 'transactions'
    allow_empty = True

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super().get_context_data(**kwargs)
        category = get_object_or_404(Category, pk=self.kwargs['category_id'])
        year = self.kwargs['year']
        month = self.kwargs['month']
        currency = get_object_or_404(Currency, pk=self.kwargs['currency_id'])
        if currency.id == DEFAULT_BASE_CURRENCY_2:
            num_base_currency = 2
        else:
            num_base_currency = 1
        return_url = self.kwargs['return_url']
        if return_url[0:1] != '/':
            return_url = '/' + return_url
        c_def = self.get_user_context(title='Операции с категорией - ' + str(category.name) + ' в периоде ' +
                                            str(year).zfill(4) + ' ' + str(month).zfill(2) + ' в ' + currency.iso_code,
                                      category=category,
                                      currency_iso=currency.iso_code,
                                      num_base_currency=num_base_currency,
                                      year=year,
                                      month=month,
                                      work_menu=True,
                                      selected_menu='current_state',
                                      return_url=return_url)
        return dict(list(context.items()) + list(c_def.items()))

    def dispatch(self, request, *args, **kwargs):
        category_id = self.kwargs['category_id']
        year = self.kwargs['year']
        month = self.kwargs['month']
        budget_id = self.kwargs['budget_id']
        if request.user.is_authenticated:
            if not (hasattr(request.user, 'profile') and request.user.profile.budget):
                return redirect('home')
            if budget_id != request.user.profile.budget.pk:
                return self.handle_no_permission()

        self.queryset = (Transaction.objects
                         .distinct()
                         .filter(budget_id=budget_id,
                                 budget_year=year,
                                 budget_month=month,
                                 transaction_categories__category__id=category_id
                                 )
                         .order_by('-time_transaction')
                         .select_related('budget', 'account', 'currency', 'sender'))
        return super(AccountTransactionsInCategoryPeriod, self).dispatch(request, *args, **kwargs)
