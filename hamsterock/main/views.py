from django.contrib.auth import logout
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordChangeDoneView
from django.http import HttpResponseNotFound, HttpResponseForbidden
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



