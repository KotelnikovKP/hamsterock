from django import template

from ..models import *

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
        else:
            menu = [{'title': "Начать вести бюджет", 'url_name': 'start_budget'},
                    {'title': "О сервисе", 'url_name': 'about'},
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


@register.inclusion_tag('main/menu_work.html')
def show_work_left_menu(selected_menu=None, user=None, budget=None, accounts=None, account_selected=None,
                        is_owner_budget=None, budget_years=None, budget_year_selected=None,
                        base_currencies=None, base_currency_selected=None,
                        month_shifts=None, month_shift_selected=None):
    return {'selected_menu': selected_menu, 'user': user, 'budget': budget, 'accounts': accounts,
            'account_selected': account_selected, 'is_owner_budget': is_owner_budget, 'budget_years': budget_years,
            'budget_year_selected': budget_year_selected, 'base_currencies': base_currencies,
            'base_currency_selected': base_currency_selected, 'month_shifts': month_shifts,
            'month_shift_selected': month_shift_selected}


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


@register.filter(name='negative')
def negative_value(value):
    return -value


@register.filter(name='multiply')
def multiply(value, factor):
    return value * factor


@register.filter(name='addstr')
def addstr(value, term):
    return value + str(term)


@register.simple_tag(name='getcats')
def get_categories(tr=None):
    class CategoriesSummary:
        def __init__(self, category_quantity=0, sum_amount=0, category_list=None):
            if category_list is None:
                category_list = []
            self.category_quantity = category_quantity
            self.sum_amount = sum_amount
            self.category_list = category_list

    tks = TransactionCategory.objects.filter(transaction_id=tr.pk)
    cq = len(tks)
    sa = ftod(0.00, 2)
    cl = []
    for tk in tks:
        sa = sa + ftod(tk.amount_acc_cur, 2)
        amount = tk.amount_acc_cur if tk.transaction.type in ('CRE', 'MO+', 'ED+') else -tk.amount_acc_cur
        cl.append(tk.category.name + ': ' + number_format(amount, decimal_pos=2, use_l10n=True, force_grouping=True))
    return CategoriesSummary(cq, sa, cl)


@register.simple_tag(name='getcatsextra')
def get_categories_extra(tr, num_base_currency):
    class CategoriesSummary:
        def __init__(self, category_quantity=0, sum_amount=0, category_list=None):
            if category_list is None:
                category_list = []
            self.category_quantity = category_quantity
            self.sum_amount = sum_amount
            self.category_list = category_list

    tks = TransactionCategory.objects.filter(transaction_id=tr.pk)
    cq = len(tks)
    sa = ftod(0.00, 2)
    cl = []
    for tk in tks:
        sa = sa + ftod(tk.amount_acc_cur, 2)
        amount = tk.amount_acc_cur if tk.transaction.type in ('CRE', 'MO+', 'ED+') else -tk.amount_acc_cur
        if num_base_currency == 1:
            amount_base = tk.amount_base_cur_1 \
                if tk.transaction.type in ('CRE', 'MO+', 'ED+') \
                else -tk.amount_base_cur_1
            cur_iso = Currency.objects.get(pk=DEFAULT_BASE_CURRENCY_1).iso_code
        else:
            amount_base = tk.amount_base_cur_2 \
                if tk.transaction.type in ('CRE', 'MO+', 'ED+') \
                else -tk.amount_base_cur_2
            cur_iso = Currency.objects.get(pk=DEFAULT_BASE_CURRENCY_2).iso_code
        cl.append(tk.category.name + ': ' + number_format(amount, decimal_pos=2, use_l10n=True, force_grouping=True) +
                  ' (' + number_format(amount_base, decimal_pos=2, use_l10n=True, force_grouping=True) + ' ' +
                  cur_iso + ')')
    return CategoriesSummary(cq, sa, cl)


@register.simple_tag(name='getperiod')
def get_period(budget_year=None, budget_month=None):
    return str(budget_year).zfill(4) + ' ' + str(budget_month).zfill(2)


@register.simple_tag(name='get_value_from_dict')
def get_value_from_dict(dict_data, key0, key1=None, key2=None, key3=None, key4=None,
                        key5=None, key6=None, key7=None, key8=None, key9=None):
    try:
        if key9:
            return dict_data[key0][key1][key2][key3][key4][key5][key6][key7][key8].get(key9)
        elif key8:
            return dict_data[key0][key1][key2][key3][key4][key5][key6][key7].get(key8)
        elif key7:
            return dict_data[key0][key1][key2][key3][key4][key5][key6].get(key7)
        elif key6:
            return dict_data[key0][key1][key2][key3][key4][key5].get(key6)
        elif key5:
            return dict_data[key0][key1][key2][key3][key4].get(key5)
        elif key4:
            return dict_data[key0][key1][key2][key3].get(key4)
        elif key3:
            return dict_data[key0][key1][key2].get(key3)
        elif key2:
            return dict_data[key0][key1].get(key2)
        elif key1:
            return dict_data[key0].get(key1)
        elif key0:
            return dict_data.get(key0)
    except Exception as e:
        return None


@register.simple_tag(name='strong_str')
def strong_str(string=None):
    res = ''
    un_processed_string = string
    while un_processed_string:
        pos = un_processed_string.find('<')
        if pos != -1:
            if pos != 0:
                res += '&nbsp;'.join(un_processed_string[:pos].split())
            un_processed_string = un_processed_string[pos:]
            pos = un_processed_string.find('>')
            if pos != -1:
                res += un_processed_string[:pos+1]
                un_processed_string = un_processed_string[pos+1:]
            else:
                res += un_processed_string
                un_processed_string = ''
        else:
            res += '&nbsp;'.join(un_processed_string.split())
            un_processed_string = ''
    return res


@register.filter
def create_range(value, start_index=0):
    return range(start_index, value+start_index)


@register.filter
def form_format(value):
    return f"{value:.2f}"


@register.simple_tag(name='get_node_id')
def get_node_id(direction, cat_id, cat_parent_id):
    return direction + '-' + str(cat_id) \
        if cat_parent_id == 0 \
        else direction + '-' + str(cat_parent_id) + '-' + str(cat_id)


@register.simple_tag(name='get_bal_node_id')
def get_bal_node_id(direction, bal_id, bal_parent_id, bal_parent_parent_id):
    bal_node_id = direction
    if not bal_id:
        bal_node_id = bal_node_id + '-0'
    elif not bal_parent_id:
        bal_node_id = bal_node_id + '-0-' + str(bal_id)
    elif not bal_parent_parent_id:
        bal_node_id = bal_node_id + '-0-' + str(bal_parent_id) + '-' + str(bal_id)
    else:
        bal_node_id = bal_node_id + '-0-' + str(bal_parent_parent_id) + '-' + str(bal_parent_id) + '-' + str(bal_id)
    return bal_node_id


@register.simple_tag(name='get_field_name_without_suffix')
def get_field_name_without_suffix(value):
    pos = value.rfind('_')
    return value if pos == -1 or not value[pos+1:].isdigit() else value[:pos]


@register.simple_tag(name='get_list_item')
def get_list_item(value, idx):
    return value[idx]


@register.filter(name='isnull')
def isnull(value):
    return value is None


@register.simple_tag(name='get_month_shift_name')
def get_month_shift_name(value):
    d = datetime.utcnow()
    d = datetime(d.year, d.month, 1, 0, 0, 0, 0, timezone.utc)
    for m in range(value):
        d = d - timedelta(days=1)
        d = datetime(d.year, d.month, 1, 0, 0, 0, 0, timezone.utc)
    if value == 0:
        s = 'Текущий '
    elif value == 1:
        s = 'Предыдущий '
    else:
        s = ''
    return s + str(d.year).zfill(4) + ' ' + str(d.month).zfill(2)


@register.simple_tag(name='get_value_from_list')
def get_value_from_list(list_data, idx):
    try:
        return list_data[idx]
    except Exception as e:
        return None


@register.simple_tag(name='get_path_wit_cat')
def get_path_wit_cat(path, cat_id):
    return path + '?cat_id=' + str(cat_id)


@register.filter(name='add_slash')
def add_slash(value):
    return '/' + value if value[0:1] != '/' else value
