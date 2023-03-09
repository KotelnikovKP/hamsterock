from django.urls import path

from .views import *

urlpatterns = [
    path('', home, name='home'),
    path('about/', about, name='about'),
    path('contact/', ContactFormView.as_view(), name='contact'),
    path('login/', LoginUser.as_view(), name='login'),
    path('logout/', logout_user, name='logout'),
    path('password-change/', PasswordChange.as_view(), name='password_change'),
    path('password-change/done/', PasswordChangeDone.as_view(), name='password_change_done'),
    path('register/', register, name='register'),
    path('edit_user/', edit_user, name='edit_user'),
    path('start_budget/', start_budget, name='start_budget'),
    path('edit_budget/', edit_budget, name='edit_budget'),
    path('show_budget/', show_budget, name='show_budget'),
    path('budget_users/', budget_users, name='budget_users'),
    path('remove_user_from_budget/<int:user_id>/<path:return_url>/', remove_user_from_budget,
         name='remove_user_from_budget'),
]
