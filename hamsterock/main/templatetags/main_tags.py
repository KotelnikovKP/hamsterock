from django import template

register = template.Library()


@register.inclusion_tag('main/menu_main.html')
def show_main_menu(is_authenticated=False, username='', is_staff=None, avatar=None, is_has_budget=None, first_account=0,
                   is_owner_budget=None, first_budget_year=0, first_base_currency=0):
    if is_authenticated:
        if is_has_budget:
            if first_account == 0:
                if is_owner_budget:
                    menu = [{'title': "Добавить первый счет/кошелек", 'url_name': 'add_account'},
                            {'title': "Настройки бюджета", 'url_name': 'edit_budget'},
                            {'title': "О сервисе", 'url_name': 'about'},
                            ]
                else:
                    menu = [{'title': "Добавить первый счет/кошелек", 'url_name': 'no_account'},
                            {'title': "О сервисе", 'url_name': 'about'},
                            ]
            else:
                if is_owner_budget:
                    menu = [{'title': "Текущее состояние", 'url_name': 'current_state',
                             'url_suffix': first_base_currency, 'url_suffix_2': 0},
                            {'title': "Счета и операции", 'url_name': 'account_transactions',
                             'url_suffix': first_account},
                            {'title': "Годовой бюджет", 'url_name': 'annual_budget', 'url_suffix': first_budget_year,
                             'url_suffix_2': first_base_currency},
                            {'title': "Настройки бюджета", 'url_name': 'edit_budget'},
                            {'title': "О сервисе", 'url_name': 'about'},
                            ]
                else:
                    menu = [{'title': "Текущее состояние", 'url_name': 'current_state',
                             'url_suffix': first_base_currency, 'url_suffix_2': 0},
                            {'title': "Счета и операции", 'url_name': 'account_transactions',
                             'url_suffix': first_account},
                            {'title': "Годовой бюджет", 'url_name': 'annual_budget', 'url_suffix': first_budget_year,
                             'url_suffix_2': first_base_currency},
                            {'title': "О сервисе", 'url_name': 'about'},
                            ]
            menu = [{'title': "О сервисе", 'url_name': 'about'},
                    ]
        else:
            menu = [{'title': "Начать вести бюджет", 'url_name': 'start_budget'},
                    {'title': "О сервисе", 'url_name': 'about'},
                    ]
            menu = [{'title': "О сервисе", 'url_name': 'about'},
                    ]
    else:
        menu = [{'title': "О сервисе", 'url_name': 'about'},
                ]

    return {"menu": menu, "is_authenticated": is_authenticated, "username": username, "is_staff": is_staff,
            "avatar": avatar}


@register.simple_tag
def url_replace(request, field, value):
    d = request.GET.copy()
    d[field] = value
    return d.urlencode()


@register.inclusion_tag('main/menu_unauthenticated.html')
def show_unauthenticated_left_menu(selected_menu=None):
    return {'selected_menu': selected_menu}


@register.inclusion_tag('main/menu_profile.html')
def show_profile_left_menu(selected_menu=None, is_has_budget=None, is_owner_budget=None, user=None):
    return {'selected_menu': selected_menu, 'is_has_budget': is_has_budget, 'is_owner_budget': is_owner_budget,
            'user': user}


@register.simple_tag(name='get_width')
def get_width(value):
    if value < 1000:
        width = 30
    elif value < 10000:
        width = 40
    elif value < 100000:
        width = 50
    elif value < 1000000:
        width = 60
    else:
        width = 70
    return width


