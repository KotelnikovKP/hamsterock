from uuid import uuid4

from django.contrib.auth import logout, login
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordChangeDoneView
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db import transaction, DataError, IntegrityError
from django.http import HttpResponseNotFound, HttpResponseForbidden, HttpResponseServerError
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.views.generic import FormView

from .forms import *
from .utils import *


def home(request):
    return render(request, 'main/index.html',
                  get_u_context(request, {'title': 'Хомячок - управление личным бюджетом!',
                                          'profile_menu': True,
                                          },))


def about(request):
    return render(request, 'main/about.html',
                  get_u_context(request, {'title': 'О сервисе "Хомячок - управление личным бюджетом!"',
                                          'profile_menu': True,
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
                            new_budget.secret_key = str(uuid4())
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



