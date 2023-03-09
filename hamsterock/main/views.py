from uuid import uuid4

from django.contrib.auth import logout, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordChangeDoneView
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction, DataError, IntegrityError
from django.http import HttpResponseNotFound, HttpResponseForbidden, HttpResponseServerError
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import FormView, CreateView, UpdateView, DeleteView

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
                  get_u_context(request, {'title': 'Добавление первого счета/кошелека',
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
        # Если есль операции по счету, то удалять счет нельзя
        # if Transaction.objects.filter(account_id=a.pk).count() > 0:
        if False:
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


@login_required
def account_transactions(request, account_id):
    """
    Функция списка операций по счету
    """
    if not request.user.is_authenticated:
        return redirect('home')
    if not (hasattr(request.user, 'profile') and request.user.profile.budget):
        return redirect('home')
    a = get_object_or_404(Account, pk=account_id)
    if request.user.profile.budget.user != request.user:
        return redirect('home')
    if a.budget != request.user.profile.budget:
        return redirect('home')
    return render(request, 'main/account_transactions.html',
                  get_u_context(request, {'title': 'Операции по счету/кошельку - ' + str(a),
                                          'account_selected': a.id,
                                          'account_currency_id': a.currency.id,
                                          'account_currency_iso': a.currency.iso_code,
                                          'account_available_balance': a.balance + a.credit_limit,
                                          'account_balance': a.balance,
                                          'account_credit_limit': a.credit_limit,
                                          'account_type': a.type,
                                          'account_budget': a.budget.id,
                                          'work_menu': True,
                                          'selected_menu': 'account_transactions'}))



