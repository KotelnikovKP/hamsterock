from django.contrib import admin
from django.utils.safestring import mark_safe

from main.models import *

admin.site.site_title = 'Админ-панель сайта "Хомячок - управление личным бюджетом!"'
admin.site.site_header = 'Админ-панель сайта "Хомячок - управление личным бюджетом!"'


class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_html_avatar', 'date_of_birth', 'budget']
    list_display_links = ('user',)
    search_fields = ('user',)
    fields = ('user', 'avatar', 'get_html_avatar', 'date_of_birth', 'budget')
    readonly_fields = ('get_html_avatar', )
    save_on_top = True

    def get_html_avatar(self, obj):
        if obj.avatar:
            return mark_safe(f"<img src='{obj.avatar.url}' width=50")

    get_html_avatar.short_description = 'Фото'


admin.site.register(Profile, ProfileAdmin)


class CurrencyAdmin(admin.ModelAdmin):
    list_display = ['name', 'iso_code', 'numeric_code', 'entity', 'is_frequently_used']
    list_display_links = ('name',)
    search_fields = ('name', 'iso_code', 'numeric_code', 'entity')
    fields = ('name', 'iso_code', 'numeric_code', 'entity', 'is_frequently_used')
    save_on_top = True
    list_editable = ('is_frequently_used',)
    list_filter = ('is_frequently_used', )


admin.site.register(Currency, CurrencyAdmin)


class BudgetAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'base_currency_1', 'base_currency_2', 'secret_key',
                    'digit_rounding', 'start_budget_month', 'end_budget_month']
    list_display_links = ('name',)
    search_fields = ('name', 'user', 'base_currency_1', 'base_currency_2', 'secret_key',
                     'digit_rounding', 'start_budget_month', 'end_budget_month')
    fields = ('name', 'user', 'base_currency_1', 'base_currency_2', 'secret_key',
              'digit_rounding', 'start_budget_month', 'end_budget_month')
    save_on_top = True
    list_filter = ('user', )


admin.site.register(Budget, BudgetAdmin)


