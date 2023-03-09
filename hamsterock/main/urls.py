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
    path('no_account/', no_account, name='no_account'),
    path('add_account/', AddAccount.as_view(), name='add_account'),
    path('edit_account/<int:account_id>/', EditAccount.as_view(), name='edit_account'),
    path('delete_account/<int:account_id>/', DeleteAccount.as_view(), name='delete_account'),
    path('projects/', Projects.as_view(), name='projects'),
    path('add_project/', AddProject.as_view(), name='add_project'),
    path('edit_project/<int:project_id>/', EditProject.as_view(), name='edit_project'),
    path('delete_project/<int:project_id>/', DeleteProject.as_view(), name='delete_project'),
    path('budget_objects/', BudgetObjects.as_view(), name='budget_objects'),
    path('add_budget_object/', AddBudgetObject.as_view(), name='add_budget_object'),
    path('edit_budget_object/<int:budget_object_id>/', EditBudgetObject.as_view(), name='edit_budget_object'),
    path('delete_budget_object/<int:budget_object_id>/', DeleteBudgetObject.as_view(), name='delete_budget_object'),
    path('account_transactions/<int:account_id>/', account_transactions, name='account_transactions'),
]
