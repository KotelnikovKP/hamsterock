from captcha.fields import CaptchaField
from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from main.models import *


class ContactForm(forms.Form):
    name = forms.CharField(label='Имя', max_length=255)
    email = forms.EmailField(label='Email')
    content = forms.CharField(label='Сообщение', widget=forms.Textarea(attrs={'cols': 60, 'rows': 10}))
    captcha = CaptchaField(label='Введите текст с картинки')


class LoginUserForm(AuthenticationForm):
    username = forms.CharField(label='Логин', widget=forms.TextInput(attrs={'class': 'form-input'}))
    password = forms.CharField(label='Пароль', widget=forms.PasswordInput(attrs={'class': 'form-input'}))


class UserRegistrationForm(forms.ModelForm):
    password1 = forms.CharField(label='Пароль',
                                strip=False,
                                widget=forms.PasswordInput(attrs={'class': 'form-input',
                                                                  'autocomplete': 'new-password'}),
                                )
    password2 = forms.CharField(label='Повтор пароля',
                                strip=False,
                                widget=forms.PasswordInput(attrs={'class': 'form-input',
                                                                  'autocomplete': 'new-password'}),
                                )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input', 'autocomplete': 'new-password'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'})
        }
        labels = {
            'username': 'Логин',
            'email': 'Email'
        }

    def clean_password2(self):
        cd = self.cleaned_data
        if cd['password1'] != cd['password2']:
            raise forms.ValidationError('Пароли не совпадают!')
        return cd['password2']

    def _post_clean(self):
        super(UserRegistrationForm, self)._post_clean()
        # Validate the password after self.instance is updated with form data
        # by super().
        password = self.cleaned_data.get("password2")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except ValidationError as error:
                self.add_error("password2", error)


class HRClearableFileInput(forms.ClearableFileInput):
    template_name = "main/user_clearable_file_input.html"


class ProfileRegistrationForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['user', 'budget', 'date_of_birth', 'time_zone', 'avatar']
        widgets = {
            'avatar': HRClearableFileInput(),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-input'}),
            'time_zone': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super(ProfileRegistrationForm, self).__init__(*args, **kwargs)
        self.fields['time_zone'].initial = ftod(0.00, 2)


class BudgetRegistrationForm(forms.ModelForm):
    is_join_to_parent_budget = forms.BooleanField(required=False,
                                                  initial=False,
                                                  label='... или присоединиться к уже существующему бюджету',
                                                  widget=forms.CheckboxInput(
                                                      attrs={'onclick': 'toggle_is_join_to_parent_budget(this.form)'}),
                                                  )

    secret_key = forms.CharField(required=False,
                                 label='Секретное слово',
                                 widget=forms.TextInput(attrs={'class': 'form-input'}),
                                 help_text='ВАЖНО! Запросите у владельца бюджета секретное слово для доступа к его '
                                           'бюджету и введите в это поле',
                                 disabled=True,
                                 )

    class Meta:
        model = Budget
        fields = ['name', 'user', 'base_currency_1', 'base_currency_2']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'base_currency_1': forms.Select(attrs={'class': 'form-input'}),
            'base_currency_2': forms.Select(attrs={'class': 'form-input'}),
        }
        labels = {
            'name': 'Начать бюджет (имя)',
            'base_currency_1': 'Основная валюта',
            'base_currency_2': 'Доп. валюта',
        }

    def __init__(self, *args, **kwargs):
        super(BudgetRegistrationForm, self).__init__(*args, **kwargs)
        post = kwargs.get('data', None)
        if post:
            if post.get('is_join_to_parent_budget', 'off') == 'on':
                self.fields['name'].required = False
                self.fields['name'].disabled = True
                self.fields['base_currency_1'].required = False
                self.fields['base_currency_1'].disabled = True
                self.fields['base_currency_2'].required = False
                self.fields['base_currency_2'].disabled = True
                self.fields['secret_key'].required = True
                self.fields['secret_key'].disabled = False
            else:
                self.fields['name'].required = True
                self.fields['name'].disabled = False
                self.fields['base_currency_1'].required = True
                self.fields['base_currency_1'].disabled = False
                self.fields['base_currency_2'].required = True
                self.fields['base_currency_2'].disabled = False
                self.fields['secret_key'].required = False
                self.fields['secret_key'].disabled = True
        self.fields['base_currency_1'].queryset = Currency.objects.filter(is_frequently_used=1)
        self.fields['base_currency_2'].queryset = Currency.objects.filter(is_frequently_used=1)
        self.fields['base_currency_1'].empty_label = '<валюта не выбрана>'
        self.fields['base_currency_2'].empty_label = '<валюта не выбрана>'
        self.fields['base_currency_2'].help_text = 'ВАЖНО! В основной и дополнительной валютах будут отображаться ' \
                                                   'итоги по категориям бюджета. Для расчета будут применяться курсы ' \
                                                   'валют на итоговые даты. '


