from uuid import uuid4

from django.contrib.auth import logout, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordChangeDoneView
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction, DataError, IntegrityError
from django.db.models import F, Value
from django.db.models.functions import Concat
from django.http import HttpResponseNotFound, HttpResponseForbidden, HttpResponseServerError
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import formats, translation
from django.views.generic import FormView, CreateView, UpdateView, DeleteView, ListView

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
