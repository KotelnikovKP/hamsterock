from captcha.fields import CaptchaField
from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, HiddenInput, inlineformset_factory
from mptt.forms import TreeNodeChoiceField

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


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input', 'disabled': 'disabled'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'})
        }
        labels = {
            'username': 'Логин',
            'email': 'Email'
        }


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['date_of_birth', 'time_zone', 'avatar']
        widgets = {
            'avatar': HRClearableFileInput(),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-input'}),
            'time_zone': forms.Select(attrs={'class': 'form-input'}),
        }
        labels = {
            'avatar': 'Фото сейчас',
        }


class ProfileStartBudgetForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['budget']


class BudgetStartBudgetForm(forms.ModelForm):
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
        super(BudgetStartBudgetForm, self).__init__(*args, **kwargs)
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


class BudgetEditForm(forms.ModelForm):
    base_currency_1 = forms.CharField(label='Основная валюта',
                                      widget=forms.TextInput(attrs={'class': 'form-input', 'readonly': 'readonly'}))
    base_currency_2 = forms.CharField(label='Доп. валюта',
                                      widget=forms.TextInput(attrs={'class': 'form-input', 'readonly': 'readonly'}))

    class Meta:
        model = Budget
        fields = ['name', 'secret_key', 'digit_rounding', 'start_budget_month', 'end_budget_month']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'user': forms.Select(attrs={'class': 'form-input'}),
            'secret_key': forms.TextInput(attrs={'class': 'form-input'}),
            'digit_rounding': forms.Select(attrs={'class': 'form-input'}),
            'start_budget_month': forms.Select(attrs={'class': 'form-input'}),
            'end_budget_month': forms.Select(attrs={'class': 'form-input'}),
        }
        labels = {
            'name': 'Имя бюджета',
            'secret_key': 'Секретное слово',
        }

    def __init__(self, *args, **kwargs):
        super(BudgetEditForm, self).__init__(*args, **kwargs)
        self.fields['secret_key'].help_text = 'ВАЖНО! Сообщите секретное слово из этого поля пользователю, которого ' \
                                              'вы хотите подключить к ведению вашего бюджета. Рекомендуется менять ' \
                                              'секретное слово после присоединения нового пользователя.'
        self.fields['base_currency_2'].help_text = 'ВАЖНО! В основной и дополнительной валютах будут отображаться ' \
                                                   'итоги по категориям бюджета. Для расчета будут применяться курсы ' \
                                                   'валют на итоговые даты. '


class BudgetShowForm(forms.Form):
    name = forms.CharField(label='Имя бюджета',
                           widget=forms.TextInput(attrs={'class': 'form-input', 'readonly': 'readonly'}))
    user = forms.CharField(label='Владелец бюджета',
                           widget=forms.TextInput(attrs={'class': 'form-input', 'readonly': 'readonly'}))
    digit_rounding = forms.CharField(label='Округление плановых значений',
                                     widget=forms.TextInput(attrs={'class': 'form-input', 'readonly': 'readonly'}))
    start_budget_month = forms.CharField(label='Месяц начала планирования бюджета следующего года',
                                         widget=forms.TextInput(attrs={'class': 'form-input', 'readonly': 'readonly'}))
    end_budget_month = forms.CharField(label='Месяц окончания планирования бюджета текущего года',
                                       widget=forms.TextInput(attrs={'class': 'form-input', 'readonly': 'readonly'}))
    base_currency_1 = forms.CharField(label='Основная валюта',
                                      widget=forms.TextInput(attrs={'class': 'form-input', 'readonly': 'readonly'}))
    base_currency_2 = forms.CharField(label='Доп. валюта',
                                      widget=forms.TextInput(attrs={'class': 'form-input', 'readonly': 'readonly'}))

    def __init__(self, *args, **kwargs):
        super(BudgetShowForm, self).__init__(*args, **kwargs)
        self.fields['base_currency_2'].help_text = 'ВАЖНО! В основной и дополнительной валютах будут отображаться ' \
                                                   'итоги по категориям бюджета. Для расчета будут применяться курсы ' \
                                                   'валют на итоговые даты. '


class RemoveUserFromBudgetForm(forms.Form):
    pass


class AddAccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['type', 'name', 'currency', 'credit_limit', 'initial_balance', 'time_zone']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-input'}),
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'currency': forms.Select(attrs={'class': 'form-input'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-input', 'value': '0.00', 'step': '0.01'}),
            'initial_balance': forms.NumberInput(attrs={'class': 'form-input', 'value': '0.00', 'step': '0.01'}),
            'time_zone': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super(AddAccountForm, self).__init__(*args, **kwargs)
        self.fields['currency'].queryset = Currency.objects.filter(is_frequently_used=1)
        self.fields['currency'].empty_label = '<валюта не выбрана>'
        self.fields['credit_limit'].help_text = 'ВАЖНО! Укажите установленный банком кредитный лимит (лимит ' \
                                                'овердрафта). Действует для кредитных счетов/крат. '
        self.fields['initial_balance'].help_text = 'ВАЖНО! Укажите остаток по счету/кошельку на утро даты, ' \
                                                   'с которой будут загружены операции по нему в систему '


class EditAccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['type', 'name', 'balance', 'credit_limit', 'initial_balance', 'time_zone']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-input'}),
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'balance': forms.NumberInput(attrs={'class': 'form-input', 'readonly': 'readonly', 'step': '0.01'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'initial_balance': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'time_zone': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super(EditAccountForm, self).__init__(*args, **kwargs)
        self.fields['credit_limit'].help_text = 'ВАЖНО! Укажите установленный банком кредитный лимит (лимит ' \
                                                'овердрафта). Действует для кредитных счетов/крат. '
        self.fields['initial_balance'].help_text = 'ВАЖНО! Укажите остаток по счету/кошельку на утро даты, ' \
                                                   'с которой будут загружены операции по нему в систему '


class AddProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'is_project_completed']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super(AddProjectForm, self).__init__(*args, **kwargs)


class EditProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'is_project_completed']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super(EditProjectForm, self).__init__(*args, **kwargs)


class AddBudgetObjectForm(forms.ModelForm):
    class Meta:
        model = BudgetObject
        fields = ['name', 'object_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'object_type': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super(AddBudgetObjectForm, self).__init__(*args, **kwargs)


class EditBudgetObjectForm(forms.ModelForm):
    class Meta:
        model = BudgetObject
        fields = ['name', 'object_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'object_type': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super(EditBudgetObjectForm, self).__init__(*args, **kwargs)


class TransactionAddForm(forms.ModelForm):
    form_time_transaction = \
        forms.DateTimeField(label='Дата-время операции',
                            widget=forms.DateTimeInput(attrs={'class': 'form-input'}))

    class Meta:
        model = Transaction
        fields = ['type', 'time_transaction', 'form_time_transaction', 'time_zone', 'amount_acc_cur', 'currency',
                  'amount', 'place', 'description', 'project', 'mcc_code', 'banks_category', 'banks_description',
                  'budget_year', 'budget_month', 'budget', 'account', 'user_create', 'user_update']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-input', 'onchange': 'change_type(this.form)'}),
            'time_transaction': forms.DateTimeInput(attrs={'class': 'form-input'}),
            'time_zone': forms.Select(attrs={'class': 'form-input'}),
            'amount_acc_cur': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'currency': forms.Select(attrs={'class': 'form-input', 'onchange': 'change_currency(this.form)'}),
            'amount': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'place': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.TextInput(attrs={'class': 'form-input'}),
            'project': forms.Select(attrs={'class': 'form-input'}),
            'mcc_code': forms.TextInput(attrs={'class': 'form-input'}),
            'banks_category': forms.TextInput(attrs={'class': 'form-input'}),
            'banks_description': forms.TextInput(attrs={'class': 'form-input'}),
            'budget_year': forms.NumberInput(attrs={'class': 'form-input'}),
            'budget_month': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, budget_id, *args, **kwargs):
        super(TransactionAddForm, self).__init__(*args, **kwargs)
        self.fields['currency'].queryset = Currency.objects.filter(is_frequently_used=1)
        self.fields['currency'].empty_label = '<валюта не выбрана>'
        self.fields['type'].help_text = 'ВАЖНО! Для операции с типом "Перемещение приход" сумма и валюта операции ' \
                                        'должны быть такими же как у операции счета-источника '
        self.fields['project'].queryset = Project.objects.filter(budget_id=budget_id, is_project_completed=0)
        self.fields['project'].empty_label = '<текущий приход/расход>'

    def clean_budget_year(self):
        budget_year = None
        if self.cleaned_data:
            budget_year = self.cleaned_data['budget_year']
            if budget_year < MIN_BUDGET_YEAR or budget_year > MAX_BUDGET_YEAR:
                self.add_error("budget_year", forms.ValidationError('Укажите корректный год!'))
        return budget_year

    def clean_time_transaction(self):
        time_transaction = None
        if self.cleaned_data:
            time_transaction = self.cleaned_data['time_transaction']
            if time_transaction < MIN_TRANSACTION_DATETIME or \
                    time_transaction > MAX_TRANSACTION_DATETIME:
                self.add_error("time_transaction", forms.ValidationError('Укажите корректную дату!'))
        return time_transaction

    def clean_amount_acc_cur(self):
        amount_acc_cur = None
        if self.cleaned_data:
            amount_acc_cur = self.cleaned_data['amount_acc_cur']
            if not amount_acc_cur:
                self.add_error("amount_acc_cur", forms.ValidationError('Сумма должна быть отличной от нуля!'))
        return amount_acc_cur


class TransactionCategoryAddForm(forms.ModelForm):
    category_inc = TreeNodeChoiceField(label='Категория прихода',
                                       widget=forms.Select(attrs={'class': 'form-input'}),
                                       queryset=Category.objects.filter(type='INC', budget_id__isnull=True).exclude(
                                           pk=POSITIVE_EXCHANGE_DIFFERENCE),
                                       level_indicator='···',
                                       empty_label='<категория не выбрана>',
                                       required=False
                                       )
    category_exp = TreeNodeChoiceField(label='Категория расхода',
                                       widget=forms.Select(attrs={'class': 'form-input'}),
                                       queryset=Category.objects.filter(type='EXP', budget_id__isnull=True).exclude(
                                           pk=NEGATIVE_EXCHANGE_DIFFERENCE),
                                       level_indicator='···',
                                       empty_label='<категория не выбрана>',
                                       required=False
                                       )
    budget_object = forms.ChoiceField(label='Объект бюджета',
                                      widget=forms.Select(attrs={'class': 'form-input'}),
                                      required=False
                                      )

    class Meta:
        model = TransactionCategory
        fields = ['transaction', 'category', 'amount_acc_cur', 'budget_year', 'budget_month']

    def __init__(self, budget_id, *args, **kwargs):
        super(TransactionCategoryAddForm, self).__init__(*args, **kwargs)
        budget_objects = [(budget_object.id, str(budget_object))
                          for budget_object in BudgetObject.objects.filter(budget_id=budget_id)]
        budget_objects.insert(0, (None, '<не задано>'))
        self.fields['budget_object'].choices = budget_objects

    def clean_category_inc(self):
        category = None
        if self.cleaned_data:
            category = self.cleaned_data['category_inc']
            if category and category.parent is None:
                self.add_error("category_inc", forms.ValidationError('Выберите категорию второго уровня!'))
        return category

    def clean_category_exp(self):
        category = None
        if self.cleaned_data:
            category = self.cleaned_data['category_exp']
            if category and category.parent is None:
                self.add_error("category_exp", forms.ValidationError('Выберите категорию второго уровня!'))
        return category


class TransactionEditForm(forms.ModelForm):
    form_time_transaction = \
        forms.DateTimeField(label='Дата-время операции',
                            widget=forms.DateTimeInput(attrs={'class': 'form-input'}))

    class Meta:
        model = Transaction
        fields = ['type', 'time_transaction', 'form_time_transaction', 'time_zone', 'amount_acc_cur', 'currency',
                  'amount', 'place', 'description', 'project', 'mcc_code', 'banks_category', 'banks_description',
                  'budget_year', 'budget_month']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-input'}),
            'time_transaction': forms.DateTimeInput(attrs={'class': 'form-input'}),
            'time_zone': forms.Select(attrs={'class': 'form-input'}),
            'amount_acc_cur': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'currency': forms.Select(attrs={'class': 'form-input', 'onchange': 'change_currency(this.form)'}),
            'amount': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'place': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.TextInput(attrs={'class': 'form-input'}),
            'project': forms.Select(attrs={'class': 'form-input'}),
            'mcc_code': forms.TextInput(attrs={'class': 'form-input'}),
            'banks_category': forms.TextInput(attrs={'class': 'form-input'}),
            'banks_description': forms.TextInput(attrs={'class': 'form-input'}),
            'budget_year': forms.NumberInput(attrs={'class': 'form-input'}),
            'budget_month': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, budget_id, is_linked_movement, *args, **kwargs):
        super(TransactionEditForm, self).__init__(*args, **kwargs)
        self.fields['project'].queryset = Project.objects.filter(budget_id=budget_id, is_project_completed=0)
        self.fields['project'].empty_label = '<текущий приход/расход>'
        self.fields['type'].help_text = 'ВАЖНО! Для операции с типом "Перемещение приход" сумма и валюта ' \
                                        'операции должны быть такими же как у операции счета-источника '

        self.fields['type'].required = False
        self.fields['type'].disabled = True
        if is_linked_movement:
            self.fields['time_transaction'].required = False
            self.fields['time_transaction'].disabled = True
            self.fields['form_time_transaction'].required = False
            self.fields['form_time_transaction'].disabled = True
            self.fields['time_zone'].required = False
            self.fields['time_zone'].disabled = True
            if self.instance.type == 'MO+':
                self.fields['form_time_transaction'].help_text = 'ВАЖНО! Для изменения даты-времени, часового пояса, ' \
                                                                 'суммы и валюты операции "Перемещение приход" нужно ' \
                                                                 'сначала удалить связь с операцией-источником'
            else:
                self.fields['form_time_transaction'].help_text = 'ВАЖНО! Для изменения даты-времени, часового пояса, ' \
                                                                 'суммы и валюты операции "Перемещение расход" нужно ' \
                                                                 'сначала удалить связь с операцией-получателем'
            self.fields['currency'].required = False
            self.fields['currency'].disabled = True
            self.fields['currency'].queryset = Currency.objects.filter(id=self.instance.currency.id)
            self.fields['currency'].empty_label = '<валюта не выбрана>'
            self.fields['amount_acc_cur'].required = False
            self.fields['amount_acc_cur'].disabled = True
            self.fields['amount'].required = False
            self.fields['amount'].disabled = True
        else:
            self.fields['currency'].queryset = Currency.objects.filter(is_frequently_used=1)
            self.fields['currency'].empty_label = '<валюта не выбрана>'

    def get_initial_for_field(self, field, field_name):
        if self.instance.type in ['DEB', 'MO-'] and field_name == 'amount_acc_cur' and \
                self.instance.amount_acc_cur != ftod(0.00, 2):
            return -self.instance.amount_acc_cur
        elif self.instance.type in ['DEB', 'MO-'] and field_name == 'amount' and \
                self.instance.amount != ftod(0.00, 2):
            return -self.instance.amount
        else:
            return super(TransactionEditForm, self).get_initial_for_field(field, field_name)

    def clean_budget_year(self):
        budget_year = None
        if self.cleaned_data:
            budget_year = self.cleaned_data['budget_year']
            if budget_year < MIN_BUDGET_YEAR or budget_year > MAX_BUDGET_YEAR:
                self.add_error("budget_year", forms.ValidationError('Укажите корректный год!'))
        return budget_year

    def clean_time_transaction(self):
        time_transaction = None
        if self.cleaned_data:
            time_transaction = self.cleaned_data['time_transaction']
            if time_transaction < MIN_TRANSACTION_DATETIME or \
                    time_transaction > MAX_TRANSACTION_DATETIME:
                self.add_error("time_transaction", forms.ValidationError('Укажите корректную дату!'))
        return time_transaction

    def clean_amount_acc_cur(self):
        amount_acc_cur = None
        if self.cleaned_data:
            amount_acc_cur = self.cleaned_data['amount_acc_cur']
            if not amount_acc_cur:
                self.add_error("amount_acc_cur", forms.ValidationError('Сумма должна быть отличной от нуля!'))
        return amount_acc_cur


class TransactionCategoryEditForm(forms.ModelForm):
    category_form = TreeNodeChoiceField(label='Категория',
                                        widget=forms.Select(attrs={'class': 'form-input'}),
                                        queryset=Category.objects.filter(type='EXP', budget_id__isnull=True),
                                        level_indicator='···',
                                        empty_label='<категория не выбрана>',
                                        required=False
                                        )
    budget_object = forms.ChoiceField(label='Объект бюджета',
                                      widget=forms.Select(attrs={'class': 'form-input'}),
                                      required=False
                                      )
    parent_transaction = None

    class Meta:
        model = TransactionCategory
        fields = ['category', 'category_form', 'budget_object', 'amount_acc_cur']
        field_classes = {
            'category': TreeNodeChoiceField,
        }
        widgets = {
            'category': forms.Select(attrs={'class': 'form-input'}),
            'amount_acc_cur': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
        }

    def __init__(self, parent, *args, **kwargs):
        super(TransactionCategoryEditForm, self).__init__(*args, **kwargs)
        self.parent_transaction = parent
        typ = 'INC' if self.parent_transaction.type == 'CRE' else \
            'EXP' if self.parent_transaction.type == 'DEB' else 'NON'
        exclude_category = POSITIVE_EXCHANGE_DIFFERENCE if self.parent_transaction.type == 'CRE' else \
            NEGATIVE_EXCHANGE_DIFFERENCE if self.parent_transaction.type == 'DEB' else 'NON'
        self.fields['category'].queryset = Category.objects.filter(type=typ).exclude(pk=exclude_category)
        self.fields['category'].level_indicator = '···'
        self.fields['category'].empty_label = '<категория не выбрана>'
        self.fields['category'].required = False
        self.fields['category_form'].queryset = Category.objects.filter(type=typ, budget_id__isnull=True).exclude(
            pk=exclude_category)
        if hasattr(self.instance, 'category'):
            if self.instance.category:
                self.fields['category_form'].initial = self.instance.category.get_common_category_id()
        budget_objects = [(budget_object.id, str(budget_object))
                          for budget_object in BudgetObject.objects.filter(budget_id=parent.budget.pk)]
        budget_objects.insert(0, (None, '<не задано>'))
        self.fields['budget_object'].choices = budget_objects
        if hasattr(self.instance, 'category'):
            if self.instance.category:
                if self.instance.category.budget_object:
                    self.fields['budget_object'].initial = self.instance.category.budget_object.pk

    def get_initial_for_field(self, field, field_name):
        if self.parent_transaction.type in ['DEB', 'MO-'] and field_name == 'amount_acc_cur' and \
                self.instance.amount_acc_cur != ftod(0.00, 2):
            return -self.instance.amount_acc_cur
        else:
            return super(TransactionCategoryEditForm, self).get_initial_for_field(field, field_name)

    def clean_category(self):
        category = None
        if self.cleaned_data:
            category = self.cleaned_data['category']
            if category and category.parent is None:
                self.add_error("category", forms.ValidationError('Выберите категорию второго уровня!'))
        return category

    def clean_category_form(self):
        category = None
        if self.cleaned_data:
            category = self.cleaned_data['category_form']
            if category and category.parent is None:
                self.add_error("category_form", forms.ValidationError('Выберите категорию второго уровня!'))
        return category

    def clean_amount_acc_cur(self):
        amount_acc_cur = None
        if self.cleaned_data:
            amount_acc_cur = self.cleaned_data['amount_acc_cur']
            category = self.cleaned_data['category']
            if category and amount_acc_cur == 0.00:
                self.add_error("amount_acc_cur", forms.ValidationError('Сумма не может равняться нулю!'))
        return amount_acc_cur


class BaseTransactionCategoryFormset(BaseInlineFormSet):
    deletion_widget = HiddenInput

    def clean(self):
        result = super(BaseTransactionCategoryFormset, self).clean()

        categories = []
        amount = ftod(0.00, 2)
        last_form = None
        for form in self.forms:
            if form.cleaned_data:
                category = form.cleaned_data.get('category', None)
                if category:
                    if category in categories:
                        form.add_error("category",
                                       forms.ValidationError('Категории в списке не должны дублироваться!'))
                        form.add_error("category_form",
                                       forms.ValidationError('Категории в списке не должны дублироваться!'))
                    categories.append(category)
                    last_form = form
                    amount = amount + ftod(form.cleaned_data.get('amount_acc_cur', 0.00), 2)
        if last_form:
            if amount != last_form.parent_transaction.amount_acc_cur:
                if last_form.parent_transaction.type in ['DEB', 'MO-']:
                    transaction_amount_acc_cur = -last_form.parent_transaction.amount_acc_cur
                else:
                    transaction_amount_acc_cur = last_form.parent_transaction.amount_acc_cur
                last_form.add_error("amount_acc_cur",
                                    forms.ValidationError('Общая сумма по категориям должна равняться: ' +
                                                          number_format(transaction_amount_acc_cur,
                                                                        decimal_pos=2, use_l10n=True,
                                                                        force_grouping=True
                                                                        )
                                                          )
                                    )
        else:
            last_form = self.forms[0]
            last_form.add_error("category", forms.ValidationError('Должна быть указана хотя бы одна категория!'))
            last_form.add_error("category_form", forms.ValidationError('Должна быть указана хотя бы одна категория!'))

        return result

    def is_valid(self):
        any_form_with_category = None
        if self.is_bound:
            for i, form in enumerate(self.forms):
                if hasattr(form, 'cleaned_data'):
                    if form.cleaned_data:
                        category = form.cleaned_data.get('category', None)
                        if not category:
                            form.cleaned_data['DELETE'] = True
                        else:
                            any_form_with_category = form
        if not any_form_with_category and hasattr(self.forms[0], 'cleaned_data'):
            self.forms[0].cleaned_data['DELETE'] = False
        result = super(BaseTransactionCategoryFormset, self).is_valid()
        return result

    def save(self, commit=True):
        result = super(BaseTransactionCategoryFormset, self).save(commit=commit)
        return result


TransactionCategoryFormset = inlineformset_factory(Transaction, TransactionCategory,
                                                   form=TransactionCategoryEditForm,
                                                   formset=BaseTransactionCategoryFormset,
                                                   can_delete=True,
                                                   extra=15,
                                                   max_num=15,
                                                   absolute_max=15,
                                                   )


class JoinConfirmationForm(forms.Form):
    old_time = forms.DateTimeField(label='old_time', widget=forms.DateTimeInput(attrs={'readonly': 'readonly'}))
    new_time = forms.DateTimeField(label='new_time', widget=forms.DateTimeInput(attrs={'readonly': 'readonly'}))
    old_currency = forms.CharField(label='old_currency', widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    new_currency = forms.CharField(label='new_currency', widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    new_currency_id = forms.IntegerField(label='new_currency_id', widget=forms.HiddenInput(attrs={}))
    old_amount = forms.DecimalField(label='old_amount', widget=forms.NumberInput(attrs={'readonly': 'readonly'}))
    new_amount = forms.DecimalField(label='new_amount', widget=forms.NumberInput(attrs={'readonly': 'readonly'}))
    old_amount_acc_cur = forms.DecimalField(label='old_amount_acc_cur',
                                            widget=forms.NumberInput(attrs={'readonly': 'readonly'}))
    new_amount_acc_cur = forms.DecimalField(label='new_amount_acc_cur',
                                            widget=forms.NumberInput(attrs={'readonly': 'readonly'}))
