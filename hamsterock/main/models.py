from datetime import datetime, timedelta, date, timezone
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Index
from django.urls import reverse
from django.utils.formats import date_format, number_format
from django.utils.safestring import mark_safe
from mptt.fields import TreeForeignKey
from mptt.models import MPTTModel

from hamsterock.settings import OXR_API_KEY
from .pyoxr import *


def ftod(val, prec=15):
    """
    Функция приведение значения к Decimal с заданной точностью
    """
    if val is None:
        val = 0.00
    return Decimal(val).quantize(Decimal(10) ** -prec)


def last_day_of_month(any_day):
    """
    Функция, возвращающая последний день месяца передаваемой даты
    """
    next_month = any_day.replace(day=28) + timedelta(days=4)
    return next_month - timedelta(days=next_month.day)


def next_year_month(year, month):
    """
    Функция инкремент пары (год, месяц)
    """
    try:
        d = date(year, month, 1).replace(day=28) + timedelta(days=4)
    except Exception as e:
        d = datetime.utcnow().date().replace(day=28) + timedelta(days=4)
    return d.year, d.month


def balance_round(balance, digit_rounding):
    """
    Функция финансового округления заданной точности
    """
    res = float(balance) * 10 ** digit_rounding
    res = int(res + (0.5 if res > 0 else -0.5))
    res = res * 10 ** -digit_rounding
    return ftod(res, 2)


DEFAULT_BUDGET_NAME = 'Бюджет семьи <ваша фамилия>'

DEFAULT_BASE_CURRENCY_1 = 97  # RUB
DEFAULT_BASE_CURRENCY_2 = 121  # USD

TIME_ZONES = [
    (ftod(-12.0, 2), '(UTC-12:00) Линия перемены дат'),
    (ftod(-11.0, 2), '(UTC-11:00) Время в формате UTC -11'),
    (ftod(-10.0, 2), '(UTC-10:00) Гавайи'),
    (ftod(-9.0, 2), '(UTC-09:00) Аляска'),
    (ftod(-8.0, 2), '(UTC-08:00) Тихоокеанское время (США и Канада)'),
    (ftod(-7.0, 2), '(UTC-07:00) Горное время (США и Канада)'),
    (ftod(-6.0, 2), '(UTC-06:00) Центральное время (США и Канада), Мехико'),
    (ftod(-5.0, 2), '(UTC-05:00) Восточное время (США и Канада), Богота, Лима'),
    (ftod(-4.0, 2), '(UTC-04:00) Атлантическое время (Канада), Каракас, Ла-Пас'),
    (ftod(-3.5, 2), '(UTC-03:30) Ньюфаундленд'),
    (ftod(-3.0, 2), '(UTC-03:00) Бразилиа, Буэнос-Айрес'),
    (ftod(-2.0, 2), '(UTC-02:00) Время в формате UTC -02'),
    (ftod(-1.0, 2), '(UTC-01:00) Азорские острова'),
    (ftod(0.0, 2), '(UTC) Время Западной Европы, Дублин, Эдинбург, Лиссабон, Лондон'),
    (ftod(1.0, 2), '(UTC+01:00) Амстердам, Берлин, Брюссель, Копенгаген, Мадрид, Париж, Рим'),
    (ftod(2.0, 2), '(UTC+02:00) Вильнюс, Иерусалим, Каир, Калининград, Киев, Рига, Таллин, Хельсинки'),
    (ftod(3.0, 2), '(UTC+03:00) Багдад, Минск, Москва, Санкт-Петербург, Стамбул'),
    (ftod(3.5, 2), '(UTC+03:30) Тегеран'),
    (ftod(4.0, 2), '(UTC+04:00) Абу-Даби, Баку, Ереван, Самара, Тбилиси'),
    (ftod(4.5, 2), '(UTC+04:30) Кабул'),
    (ftod(5.0, 2), '(UTC+05:00) Ашхабад, Душанбе, Екатеринбург, Исламабад, Ташкент'),
    (ftod(5.5, 2), '(UTC+05:30) Колката, Мумбаи, Нью-Дели, Ченнай'),
    (ftod(5.75, 2), '(UTC+05:45) Катманду'),
    (ftod(6.0, 2), '(UTC+06:00) Алматы, Астана, Дакка, Омск'),
    (ftod(7.0, 2), '(UTC+07:00) Бангкок, Джакарта, Красноярск, Новосибирск, Томск, Ханой'),
    (ftod(8.0, 2), '(UTC+08:00) Гонконг, Иркутск, Пекин, Улан-Батор, Урумчи, Чунцин'),
    (ftod(9.0, 2), '(UTC+09:00) Осака, Пхеньян, Саппоро, Сеул, Токио, Якутск'),
    (ftod(9.5, 2), '(UTC+09:30) Аделаида, Дарвин'),
    (ftod(10.0, 2), '(UTC+10:00) Владивосток, Канберра, Мельбурн, Сидней'),
    (ftod(11.0, 2), '(UTC+11:00) Магадан, Сахалин, Соломоновы о-ва, Новая Каледония'),
    (ftod(12.0, 2), '(UTC+12:00) Веллингтон, Окленд, Петропавловск-Камчатский, Фиджи'),
]

MONTHS = [
    (None, '<не выбран>'),
    (1, 'Январь'),
    (2, 'Февраль'),
    (3, 'Март'),
    (4, 'Апрель'),
    (5, 'Май'),
    (6, 'Июнь'),
    (7, 'Июль'),
    (8, 'Август'),
    (9, 'Сентябрь'),
    (10, 'Октябрь'),
    (11, 'Ноябрь'),
    (12, 'Декабрь'),
]

ROUNDING = [
    (2, 'x xxx xxx,xx - до сотых'),
    (1, 'x xxx xxx,x0 - до десятых'),
    (0, 'x xxx xxx,00 - до единиц'),
    (-1, 'x xxx xx0,00 - до десятков'),
    (-2, 'x xxx x00,00 - до сотен'),
    (-3, 'x xxx 000,00 - до тысяч'),
    (-4, 'x xx0 000,00 - до десятков тысяч'),
    (-5, 'x x00 000,00 - до сотен тысяч'),
]

ACCOUNT_TYPES = [
    (None, '<тип не выбран>'),
    ('Наличные', (
        ('WAL', 'Кошелек с наличными'),
        ('SAF', 'Сейф'),
        ('SAB', 'Банковская ячейка'),
        ('STA', 'Тайничок'),
    )
     ),
    ('Счет/карта в банке', (
        ('DEC', 'Дебетовая карта'),
        ('CUA', 'Текущий счет'),
    )
     ),
    ('Кредитный счет/карта', (
        ('CRC', 'Кредитная карта'),
        ('CRA', 'Кредитный счет'),
        ('MOA', 'Ипотечный счет'),
    )
     ),
    ('Накопления', (
        ('DEA', 'Вклад'),
        ('SAA', 'Накопительный счет'),
    )
     ),
    ('Инвестиции', (
        ('INA', 'Инвестиционный счет'),
    )
     ),
    ('Бизнес-инструменты', (
        ('BCA', 'Касса'),
        ('BSA', 'Сейф'),
        ('BCU', 'Расчетный счет'),
        ('BDC', 'Дебетовая бизнес-карта'),
        ('BCC', 'Кредитная бизнес-карта'),
        ('BCR', 'Кредитный бизнес-счет'),
        ('BDE', 'Депозит'),
    )
     ),
]
CASH_ACCOUNT = ('WAL', 'SAF', 'SAB', 'STA')
CURR_ACCOUNT = ('DEC', 'CUA')
CRED_ACCOUNT = ('CRC', 'CRA', 'MOA')
DEBT_ACCOUNT = ('DEA', 'SAA')
INVS_ACCOUNT = ('INA',)
BUSN_ACCOUNT = ('BCA', 'BSA', 'BCU', 'BDC', 'BCC', 'BCR', 'BDE')
ALL_CASH_ACCOUNT = ('WAL', 'SAF', 'SAB', 'STA', 'BCA', 'BSA')

MIN_BUDGET_YEAR = 2000
MAX_BUDGET_YEAR = 2100
MIN_TRANSACTION_DATETIME = datetime(MIN_BUDGET_YEAR, 1, 1, 0, 0, 0, 0, timezone.utc)
MAX_TRANSACTION_DATETIME = datetime(MAX_BUDGET_YEAR, 12, 31, 23, 59, 59, 999999, timezone.utc)

CATEGORY_TYPES = [
    ('INC', 'Доход'),
    ('EXP', 'Расход'),
]

OBJECT_TYPES = [
    (None, '<не выбран>'),
    ('Персона', 'Персона'),
    ('Недвижимость', 'Недвижимость'),
    ('Транспорт', 'Транспорт'),
    ('Питомец', 'Питомец'),
    ('Бизнес', 'Бизнес'),
]


class Profile(models.Model):
    """
    Расширение базовой модели Django User
    Два основных свойства:
    - budget - бюджет, к которому привязан пользователь, связь 1 бюджет - много пользователей (у пользователя только
               один бюджет
    - time_zone - основной часовой пояс пользователя, используется по-умолчанию для счетов, где в свою очередь
                  используется по-умолчанию как часовой пояс операции (время операции в системе хранится в UTC, но при
                  заведении операции вручную или при загрузке указывается реальное время и часовой пояс операции)
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    avatar = models.ImageField(null=True, blank=True, upload_to='avatars', verbose_name='Фото')
    date_of_birth = models.DateField(null=True, blank=True, verbose_name='Дата рождения')
    budget = models.ForeignKey('Budget', null=True, blank=True, on_delete=models.PROTECT, verbose_name='Бюджет семьи')
    time_zone = models.DecimalField(default=0.00, choices=TIME_ZONES, null=False, blank=False, max_digits=5,
                                    decimal_places=2, verbose_name='Часовой пояс для времени операций')

    def __str__(self):
        return 'Расширение профиля пользователя {}'.format(self.user.username)

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профиль'
        ordering = ['user']

    def get_html_avatar(self):
        if self.avatar:
            return mark_safe(f"<img src='{self.avatar.url}' width=50")

    def get_url_avatar(self):
        if self.avatar:
            return mark_safe(f'<img src="{self.avatar.url}" alt="avatar" style="max-height:60px">')


class Currency(models.Model):
    """
    Список валют мира
    Не редактируемый из интерфейса справочник, взятый с ISO 4217
    Через админку можно отобрать ограниченное число валют, доступных для выбора в интерфейсах системы
    """
    name = models.CharField(max_length=100, verbose_name='Валюта')
    iso_code = models.CharField(max_length=3, unique=True, db_index=True, verbose_name='ISO код')
    numeric_code = models.CharField(max_length=3, unique=True, verbose_name='Числовой код')
    entity = models.CharField(max_length=500, verbose_name='Страны использования')
    is_frequently_used = models.BooleanField(default=True, verbose_name='Часто используемая')

    def __str__(self):
        return self.iso_code + ' ' + self.name

    def get_absolute_url(self):
        return reverse('currency', kwargs={'currency_iso_code': self.iso_code.lower()})

    class Meta:
        verbose_name = 'Валюта'
        verbose_name_plural = 'Валюты'
        ordering = ['iso_code']


class Budget(models.Model):
    """
    Бюджет, в рамках которого ведутся счета/кошельки и операции по ним.
    Каждый пользователь присоединен к одному бюджету.
    Минимальный временной период учета бюджета для плана и факта - месяц.
    В системе предусмотрено годовое планирование и отчет по факту в разрезе месяцев, а также вывод факта бюджета
    текущего месяца и двенадцати предыдущих месяцев для отслеживания динамики.
    Предусмотрено ведение бюджета в двух валютах: базовой и дополнительной, суммы операций и остатки учитываются
    в бюджете по курсу валют к базовой и дополнительной валютам бюджета на конец месяца.
    Изначально бюджет заводит один пользователь, он становится владельцем бюджета, далее к этому бюджету могут
    присоединиться другие пользователи, используя секретное слово, которое назначает владелец бюджета.
    """
    name = models.CharField(max_length=100, db_index=True, verbose_name='Наименование бюджета')
    user = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='Владелец бюджета')
    base_currency_1 = models.ForeignKey('Currency', on_delete=models.PROTECT, related_name='base_currency_1',
                                        verbose_name='Основная валюта')
    base_currency_2 = models.ForeignKey('Currency', on_delete=models.PROTECT, related_name='base_currency_2',
                                        verbose_name='Дополнительная валюта')
    secret_key = models.CharField(max_length=100, unique=True, db_index=True, verbose_name='Секретное слово')
    digit_rounding = models.IntegerField(choices=ROUNDING, default=-2, null=False, blank=False,
                                         verbose_name='Округление плановых значений')
    start_budget_month = models.IntegerField(choices=MONTHS, default=11, null=False, blank=False,
                                             verbose_name='Месяц начала планирования бюджета следующего года')
    end_budget_month = models.IntegerField(choices=MONTHS + [(0, 'нет ограничения')], default=2, null=False,
                                           blank=False,
                                           verbose_name='Месяц окончания планирования бюджета текущего года')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('budget_users', kwargs={'budget_id': self.pk})

    class Meta:
        verbose_name = 'Бюджет'
        verbose_name_plural = 'Бюджеты'
        ordering = ['name']


class CurrencyRate(models.Model):
    """
    Курсы валют.
    Используются для расчета сумм операций и остатков по счетам/кошелькам в базовой и дополнительной валютах.
    Курсы подгружаются автоматически с openexchangerates.org с использованием пакета https://pypi.org/project/pyoxr/
    Аккаунт на openexchangerates.org имеет бесплатный тариф, поэтому подгружаются только курсы к USD, отсюда курс
    пар валют без USD вычисляется через курсы каждой валюты из пары к USD.
    Для операций текущего месяца берется курс на конец предыдущего дня, для операций предыдущих месяцев берется
    курс на конец месяца, также курс на конец месяца используется для расчета курсовой разницы за данный месяц бюджета
    """
    currency_1 = models.ForeignKey('Currency', on_delete=models.PROTECT, related_name='currency_1',
                                   verbose_name='Валюта 1')
    currency_2 = models.ForeignKey('Currency', on_delete=models.PROTECT, related_name='currency_2',
                                   verbose_name='Валюта 2')
    date_rate = models.DateField(null=False, blank=False, verbose_name='Дата курса')
    rate = models.DecimalField(default=0.00, null=False, blank=False, max_digits=19, decimal_places=9,
                               verbose_name='Курс валюты 1 к валюте 2')

    def __str__(self):
        return date_format(self.date_rate, format='SHORT_DATE_FORMAT', use_l10n=True) + ' / ' + \
               str(self.currency_1) + ' / ' + str(self.currency_2) + ' / ' + \
               number_format(self.rate, decimal_pos=9, use_l10n=True, force_grouping=True)

    def get_absolute_url(self):
        return reverse('currency_rate', kwargs={'currency_rate_id': self.pk})

    class Meta:
        verbose_name = 'Курс валюты'
        verbose_name_plural = 'Курсы валют'
        ordering = ['-date_rate']
        indexes = (Index(fields=['currency_1', 'currency_2', '-date_rate'],
                         name='cr__cur_1_cur_2_date_rate_idx'),
                   Index(fields=['currency_2', 'currency_1', '-date_rate'],
                         name='cr__cur_2_cur_1_date_rate_idx'),
                   )

    @classmethod
    def upload_rates(cls, date_rate=None, additional_symbols=None):
        """
        Загрузка курсов с openexchangerates.org
        :param date_rate: дата курса
        :param additional_symbols: список дополнительных валют (iso_codes) - по умолчанию загружаются курсы
                                   по валютам из Currency с установленным флагом is_frequently_used
        :return: True - успешная загрузка, False - загрузка не свершилась (((
        """
        if not date_rate or date_rate >= datetime.utcnow().date():
            date_rate = datetime.utcnow().date() - timedelta(days=1)

        if additional_symbols is None:
            additional_symbols = []

        symbols = [currency.iso_code for currency in Currency.objects.filter(is_frequently_used=1)]

        for s in additional_symbols:
            if s not in symbols:
                symbols.append(s)

        result = {}
        try:
            oxr_cli = OXRClient(app_id=OXR_API_KEY)
            result = oxr_cli.get_historical(date_rate.strftime("%Y-%m-%d"), symbols=symbols)

        except (OXRStatusError, OXRDecodeError) as e:
            pass

        except Exception as e:
            pass

        if not result:
            return False

        base = result.get('base', '')
        rates = result.get('rates', {})

        try:
            base_id = Currency.objects.get(iso_code=base).pk
        except Exception as e:
            base_id = None

        if not base_id:
            return False

        for iso_code, rate in rates.items():
            try:
                currency_id = Currency.objects.get(iso_code=iso_code).pk
            except Exception as e:
                currency_id = None

            if currency_id:
                try:
                    currency_rate = CurrencyRate.objects.filter(currency_1_id=currency_id, currency_2_id=base_id,
                                                                date_rate=date_rate)[0]
                    currency_rate.rate = ftod(rate, 9)
                except Exception as e:
                    currency_rate = CurrencyRate(currency_1_id=currency_id, currency_2_id=base_id,
                                                 date_rate=date_rate, rate=ftod(rate, 9))
                currency_rate.save()

        return True

    @classmethod
    def get_rate(cls, currency_1_id, currency_2_id, date_rate=None):
        """
        Получение курса пары валют на дату
        :param currency_1_id: первая валюта
        :param currency_2_id: вторая валюта
        :param date_rate: дата курса
        :return: курс валюты 1 к валюте 2
        """

        def get_native_rate(c1_id, c2_id, s_date, is_strict=True):
            """
            Получение курса пары валют на дату нативно (прямой поиск пары в CurrencyRate)
            :param c1_id: первая валюта
            :param c2_id: вторая валюта
            :param s_date: дата курса
            :param is_strict: True - строгое условие по дате курса,
                              False - поиск курса на заданную дату или ближайшую раннюю дату
            :return: курс валюты 1 к валюте 2
            """
            try:
                if is_strict:
                    c_rate = CurrencyRate.objects.filter(currency_1_id=c1_id,
                                                         currency_2_id=c2_id,
                                                         date_rate=s_date)[0].rate
                else:
                    c_rate = CurrencyRate.objects.filter(currency_1_id=c1_id,
                                                         currency_2_id=c2_id,
                                                         date_rate__lte=s_date).order_by('-date_rate')[:1][0].rate
            except:
                try:
                    if is_strict:
                        c_rate = CurrencyRate.objects.filter(currency_1_id=c2_id,
                                                             currency_2_id=c1_id,
                                                             date_rate=s_date)[0].rate
                    else:
                        c_rate = CurrencyRate.objects.filter(currency_1_id=c2_id,
                                                             currency_2_id=c1_id,
                                                             date_rate__lte=s_date).order_by('-date_rate')[:1][0].rate
                    c_rate = ftod(1 / c_rate, 9)
                except:
                    c_rate = None
            return c_rate

        def get_rate_by_usd(c1_id, c2_id, s_date, is_strict=True):
            """
            Получение курса пары валют на дату через USD
            (поиск пар "первая валюта - USD" и "вторая валюта - USD" в CurrencyRate)
            :param c1_id: первая валюта
            :param c2_id: вторая валюта
            :param s_date: дата курса
            :param is_strict: True - строгое условие по дате курса,
                              False - поиск курса на заданную дату или ближайшую раннюю дату
            :return: курс валюты 1 к валюте 2
            """
            try:
                if is_strict:
                    c1_rate = CurrencyRate.objects.filter(currency_1_id=c1_id,
                                                          currency_2_id=DEFAULT_BASE_CURRENCY_2,
                                                          date_rate=s_date)[0].rate
                else:
                    c1_rate = CurrencyRate.objects.filter(currency_1_id=c1_id,
                                                          currency_2_id=DEFAULT_BASE_CURRENCY_2,
                                                          date_rate__lte=s_date).order_by('-date_rate')[:1][0].rate
            except:
                try:
                    if is_strict:
                        c1_rate = CurrencyRate.objects.filter(currency_1_id=DEFAULT_BASE_CURRENCY_2,
                                                              currency_2_id=c1_id,
                                                              date_rate=s_date)[0].rate
                    else:
                        c1_rate = CurrencyRate.objects.filter(currency_1_id=DEFAULT_BASE_CURRENCY_2,
                                                              currency_2_id=c1_id,
                                                              date_rate__lte=s_date).order_by('-date_rate')[:1][0].rate
                    c1_rate = ftod(1 / c1_rate, 9)
                except:
                    c1_rate = None
            if c1_rate:
                try:
                    if is_strict:
                        c2_rate = CurrencyRate.objects.filter(currency_1_id=c2_id,
                                                              currency_2_id=DEFAULT_BASE_CURRENCY_2,
                                                              date_rate=s_date)[0].rate
                    else:
                        c2_rate = CurrencyRate.objects.filter(currency_1_id=c2_id,
                                                              currency_2_id=DEFAULT_BASE_CURRENCY_2,
                                                              date_rate__lte=s_date).order_by('-date_rate')[:1][0].rate
                except:
                    try:
                        if is_strict:
                            c2_rate = CurrencyRate.objects.filter(currency_1_id=DEFAULT_BASE_CURRENCY_2,
                                                                  currency_2_id=c2_id,
                                                                  date_rate=s_date)[0].rate
                        else:
                            c2_rate = CurrencyRate.objects.filter(currency_1_id=DEFAULT_BASE_CURRENCY_2,
                                                                  currency_2_id=c2_id,
                                                                  date_rate__lte=s_date).order_by('-date_rate')[:1][
                                0].rate
                        c2_rate = ftod(1 / c2_rate, 9)
                    except:
                        c2_rate = None
                if c2_rate:
                    c_rate = ftod(c1_rate / c2_rate, 9)
                else:
                    c_rate = None
            else:
                c_rate = None
            return c_rate

        # если валюта 1 равна валюте 2, то и думать нечего -> 1.000000000!!!
        if currency_1_id == currency_2_id:
            return ftod(1.00, 9)

        today = datetime.utcnow()
        if not date_rate:
            date_rate = datetime.utcnow().date()
        elif type(date_rate) == datetime:
            date_rate = date_rate.date()
        if date_rate > today.date():
            date_rate = datetime.utcnow().date()

        # Определяем дату для поиска курса
        if date_rate.year == today.year and date_rate.month == today.month:
            search_date = date_rate - timedelta(days=1)
        else:
            search_date = last_day_of_month(date(date_rate.year, date_rate.month, 1))

        # Сначала попытаемся найти курс напрямую у заданной пары, либо валюта1 к валюте2, либо валюта2 к валюте1
        currency_rate = get_native_rate(currency_1_id, currency_2_id, search_date)
        if currency_rate:
            return ftod(currency_rate, 9)

        # Не нашлось. Будем искать через USD (это DEFAULT_BASE_CURRENCY_2)
        currency_rate = get_rate_by_usd(currency_1_id, currency_2_id, search_date)
        if currency_rate:
            return ftod(currency_rate, 9)

        # Не нашлось. Загрузим курсы на дату с openexchangerates.org
        additional_symbols = []
        try:
            additional_symbols.append(Currency.objects.get(pk=currency_1_id).iso_code)
        except:
            pass
        try:
            additional_symbols.append(Currency.objects.get(pk=currency_2_id).iso_code)
        except:
            pass
        if cls.upload_rates(search_date, additional_symbols):
            # Снова попытаемся найти курс напрямую у заданной пары, либо валюта1 к валюте2, либо валюта2 к валюте1
            currency_rate = get_native_rate(currency_1_id, currency_2_id, search_date)
            if currency_rate:
                return ftod(currency_rate, 9)

            # Не нашлось. Снова будем искать через USD (это DEFAULT_BASE_CURRENCY_2)
            currency_rate = get_rate_by_usd(currency_1_id, currency_2_id, search_date)
            if currency_rate:
                return ftod(currency_rate, 9)

        # Не нашлось. Будем искать курсы на ближайшую прошлую дату
        # Снова попытаемся найти курс напрямую у заданной пары, либо валюта1 к валюте2, либо валюта2 к валюте1
        currency_rate = get_native_rate(currency_1_id, currency_2_id, search_date, False)
        if currency_rate:
            return ftod(currency_rate, 9)

        # Не нашлось. Снова будем искать через USD (это DEFAULT_BASE_CURRENCY_2)
        currency_rate = get_rate_by_usd(currency_1_id, currency_2_id, search_date, False)
        if currency_rate:
            return ftod(currency_rate, 9)
        else:
            return ftod(1.00, 9)


class Account(models.Model):
    """
    Счета/кошельки
    Расходы, доходы, остатки отчетных периодов бюджета берутся из операций, которые проводятся по счетам и кошелькам.
    Счета/кошельки заводятся в определенной валюте, имеют один из типов, которые сгруппированы в группы.
    У счета/кошелька указывается часовой пояс (по умолчанию берется из профиля пользователя) для использования как
    часовой пояс операции по умолчанию (время операции в системе хранится в UTC).
    У счета/кошелька указывается входящий остаток, от которого начинается отсчет остатков.
    Также указывается кредитный лимит, например, для кредитных карт, чтобы получать доступный остаток
    (в системе для таких счетов указывается истинный остаток, как правило, он отрицательный).
    Кроме остатка в валюте счета, также ведутся два остатка в базовой и дополнительной валютах бюджета (они расчетные).
    Остатки по счету не пересчитываются в онлайн режиме по добавлению/изменению/удалению операции по счету, для этого
    существует отдельная процедура пересчета остатков. Отсюда у счета/кошелька есть флаги валидности остатков и
    бюджетных оборотов и даты, до которых они действительны
    """
    budget = models.ForeignKey('Budget', on_delete=models.PROTECT, verbose_name='Бюджет')
    name = models.CharField(max_length=100, db_index=True, verbose_name='Наименование')
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Владелец')
    currency = models.ForeignKey('Currency', on_delete=models.PROTECT, verbose_name='Валюта')
    type = models.CharField(max_length=3, choices=ACCOUNT_TYPES, null=False, blank=False, verbose_name='Тип')
    group = models.CharField(max_length=6, null=True, blank=True, verbose_name='Группа')
    time_zone = models.DecimalField(default=0.00, choices=TIME_ZONES, null=False, blank=False, max_digits=5,
                                    decimal_places=2, verbose_name='Часовой пояс для времени операций')
    initial_balance = models.DecimalField(default=0.00, null=False, blank=False, max_digits=19, decimal_places=2,
                                          verbose_name='Входящий остаток')
    balance = models.DecimalField(default=0.00, null=False, blank=False, max_digits=19, decimal_places=2,
                                  verbose_name='Текущий остаток')
    credit_limit = models.DecimalField(default=0.00, null=False, blank=False, max_digits=19, decimal_places=2,
                                       verbose_name='Кредитный лимит')
    balance_base_cur_1 = models.DecimalField(default=0.00, null=False, blank=False, max_digits=19, decimal_places=2,
                                             verbose_name='Остаток в основной базовой валюте')
    balance_base_cur_2 = models.DecimalField(default=0.00, null=False, blank=False, max_digits=19, decimal_places=2,
                                             verbose_name='Остаток в дополнительной базовой валюте')
    is_balances_valid = models.BooleanField(default=True, verbose_name='Остатки действительны?')
    balances_valid_until = models.DateTimeField(default=MIN_TRANSACTION_DATETIME, null=False, blank=False,
                                                verbose_name='Остатки действительны до')
    is_turnovers_valid = models.BooleanField(default=True, verbose_name='Бюджетные обороты действительны?')
    turnovers_valid_until = models.DateTimeField(default=MIN_TRANSACTION_DATETIME, null=False, blank=False,
                                                 verbose_name='Бюджетные обороты действительны до')

    # Для отслеживания изменений отдельных атрибутов заводим для них original_ атрибут,
    # который заполняем начальным значением по сигналу .post_init (см. файл signals.py)
    original_initial_balance = None
    original_is_balances_valid = None
    original_balances_valid_until = None
    original_type = None

    def __str__(self):
        return self.name + ' (' + self.currency.iso_code + ')'

    def get_absolute_url(self):
        return reverse('edit_account', kwargs={'account_id': self.pk})

    def get_transactions_url(self):
        return reverse('account_transactions', kwargs={'account_id': self.pk})

    def get_delete_url(self):
        return reverse('delete_account', kwargs={'account_id': self.pk})

    class Meta:
        verbose_name = 'Счет/кошелек'
        verbose_name_plural = 'Счета/кошельки'
        ordering = ['budget', 'name']
        indexes = (Index(fields=['budget', 'is_balances_valid'], name='a__budget_is_bal_valid_idx'),
                   )

    def save(self, *args, **kwargs):
        """
        Триггер на добавление и сохранение объекта класса
        """
        is_initial_balance_change = ftod(self.original_initial_balance, 2) != ftod(self.initial_balance, 2)
        is_initial_type_change = self.original_type != self.type

        # Если изменился начальный баланс, то изменим на дельту изменения и баланс по счету,
        # и балансы в базовой и дополнительной валютах.
        # А также снесем флаг валидности остатков и дату валидности остатков перенесем на начало времен.
        if is_initial_balance_change:
            self.balance = ftod(self.balance, 2) + \
                           ftod(self.initial_balance, 2) - \
                           ftod(self.original_initial_balance, 2)

            # Заменить впоследствии на получение времени из первой операции по счету
            time_first_transaction = datetime.utcnow()

            rate_base_cur_1 = CurrencyRate.get_rate(self.budget.base_currency_1_id,
                                                    self.currency_id,
                                                    time_first_transaction)
            self.balance_base_cur_1 = ftod(self.balance_base_cur_1, 2) + \
                                      ftod(self.initial_balance * rate_base_cur_1, 2) - \
                                      ftod(self.original_initial_balance * rate_base_cur_1, 2)

            rate_base_cur_2 = CurrencyRate.get_rate(self.budget.base_currency_2_id,
                                                    self.currency_id,
                                                    time_first_transaction)
            self.balance_base_cur_2 = ftod(self.balance_base_cur_2, 2) + \
                                      ftod(self.initial_balance * rate_base_cur_2, 2) - \
                                      ftod(self.original_initial_balance * rate_base_cur_2, 2)

            self.is_balances_valid = False
            self.balances_valid_until = MIN_TRANSACTION_DATETIME

        # Если изменился тип счета/кошелька, то и группу поменяем
        if is_initial_type_change:
            if self.type in CASH_ACCOUNT:
                self.group = '1.CASH'
            elif self.type in CURR_ACCOUNT:
                self.group = '2.CURR'
            elif self.type in CRED_ACCOUNT:
                self.group = '3.CRED'
            elif self.type in DEBT_ACCOUNT:
                self.group = '4.DEBT'
            elif self.type in INVS_ACCOUNT:
                self.group = '5.INVS'
            elif self.type in BUSN_ACCOUNT:
                self.group = '6.BUSN'

        super(Account, self).save(*args, **kwargs)


class AccountTurnover(models.Model):
    """
    Бюджетные обороты по счету
    Полностью расчетная модель, содержащая остаток на начало, сумму прихода, сумму расхода и остаток на конец по счету
    за каждый период бюджета (месяц). Изменения вносятся при срабатывании триггера добавления/сохранения категорий
    операций по счету/кошельку при изменении оных вручную, либо при выполнении процедуры пересчета остатков.
    Данные хранятся в базовой и дополнительной валютах бюджета.
    Модель необходима для получения остатков по счетам/кошелькам по периодам при построении годовых бюджетов.
    """
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, null=True, blank=True, verbose_name='Бюджет')
    account = models.ForeignKey('Account', on_delete=models.CASCADE, verbose_name='Счет/кошелек')
    budget_period = models.DateTimeField(null=False, blank=False, verbose_name='Период бюджета')
    begin_balance_base_cur_1 = models.DecimalField(default=0.00, null=False, blank=False,
                                                   max_digits=19, decimal_places=2,
                                                   verbose_name='Остаток на начало периода в базовой валюте')
    credit_turnover_base_cur_1 = models.DecimalField(default=0.00, null=False, blank=False,
                                                     max_digits=19, decimal_places=2,
                                                     verbose_name='Кредитовый оборот в базовой валюте')
    debit_turnover_base_cur_1 = models.DecimalField(default=0.00, null=False, blank=False,
                                                    max_digits=19, decimal_places=2,
                                                    verbose_name='Дебетовый оборот в базовой валюте')
    end_balance_base_cur_1 = models.DecimalField(default=0.00, null=False, blank=False,
                                                 max_digits=19, decimal_places=2,
                                                 verbose_name='Остаток на конец периода в базовой валюте')
    begin_balance_base_cur_2 = models.DecimalField(default=0.00, null=False, blank=False,
                                                   max_digits=19, decimal_places=2,
                                                   verbose_name='Остаток на начало периода в дополнительной валюте')
    credit_turnover_base_cur_2 = models.DecimalField(default=0.00, null=False, blank=False,
                                                     max_digits=19, decimal_places=2,
                                                     verbose_name='Кредитовый оборот в дополнительной валюте')
    debit_turnover_base_cur_2 = models.DecimalField(default=0.00, null=False, blank=False,
                                                    max_digits=19, decimal_places=2,
                                                    verbose_name='Дебетовый оборот в дополнительной валюте')
    end_balance_base_cur_2 = models.DecimalField(default=0.00, null=False, blank=False,
                                                 max_digits=19, decimal_places=2,
                                                 verbose_name='Остаток на конец периода в дополнительной валюте')

    class Meta:
        verbose_name = 'Бюджетные обороты по счету'
        verbose_name_plural = 'Бюджетные обороты по счету'
        indexes = (Index(fields=['budget', 'account', 'budget_period'],
                         name='at__budget_account_period_idx'),
                   )
        ordering = ['budget', 'account', 'budget_period']

    def __str__(self):
        return 'Бюджетные обороты по счету - ' + str(self.account) + ' ' + \
               str(self.budget_period.year) + ' ' + str(self.budget_period.month)


class Project(models.Model):
    """
    Проекты
    Доходы и расходы в бюджете поделены на два типа: текущие и проектные. Текущие доходы и расходы возникают постоянно,
    они присутствуют в каждом месяце, например, зарплата или расходы на продукты. Проектные доходы и расходы - разовые,
    уникальные, ограничены по времени, например, поездка на море, свадьба.
    В системе операцию можно отнести к проекту, тогда ее сумма будет учитываться в проектных расходах.
    Операции без указания проекта учитываются в бюджете как текущие.
    Проект имеет флаг завершенности, при установке которого проект невозможно будет выбрать для новой операции,
    при этом он останется в факте бюджета.
    """
    budget = models.ForeignKey('Budget', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Бюджет')
    name = models.CharField(max_length=100, verbose_name='Наименование')
    is_project_completed = models.BooleanField(default=False, verbose_name='Проект завершен?')

    class Meta:
        verbose_name = 'Проект'
        verbose_name_plural = 'Проекты'
        indexes = (Index(fields=['budget', 'is_project_completed'],
                         name='p__budget_is_completed_idx'),
                   )
        ordering = ['budget', 'is_project_completed']
        constraints = [
            models.UniqueConstraint(fields=['budget', 'name'], name='project__budget_name_unique'),
        ]

    def __str__(self):
        return self.name


class BudgetObject(models.Model):
    """
    Бюджетные объекты
    Бюджетный объект - это возможность разделить базовую категорию дохода или расхода на несколько по объектам
    конкретного бюджета, например, Зарплата: зарплата мужа и зарплата жены - здесь два бюджетных объекта (муж и жена).
    Также можно разделять категории доходов и расходов по детям, по питомцам, по объектам недвижимости, по транспорту.
    Для каждого бюджетного объекта в справочнике категорий заводится отдельная строка, которая имеет название
    базовой категории и после название бюджетного объекта в скобках. Также статья этой категории имеет статью
    базовой категории плюс буквенный индекс.
    """
    budget = models.ForeignKey('Budget', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Бюджет')
    object_type = models.CharField(max_length=15, choices=OBJECT_TYPES, null=False, blank=False,
                                   verbose_name='Тип объекта')
    name = models.CharField(max_length=25, verbose_name='Имя объекта')

    original_name = None

    class Meta:
        verbose_name = 'Объект бюджета'
        verbose_name_plural = 'Объекты бюджета'
        indexes = (Index(fields=['budget', 'name'], name='budget_object__budget_name_idx'),
                   )
        ordering = ['budget', 'name']
        constraints = [
            models.UniqueConstraint(fields=['budget', 'name'], name='budget_object__budget_name_unique'),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """
        Триггер на добавление/изменение
        Если изменилось название бюджетного объекта, то нужно заменить названия категорий, связанных с ним.
        """
        if self.original_name != self.name:
            categories_with_object = Category.objects.filter(budget_id=self.budget_id, budget_object_id=self.id)
            for category_with_object in categories_with_object:
                try:
                    category_with_object.name = \
                        Category.objects.get(type=category_with_object.type, item=category_with_object.item[:6]).name + \
                        ' (' + self.name + ')'
                    category_with_object.save()
                except Exception as e:
                    pass
        super(BudgetObject, self).save(*args, **kwargs)


class Category(MPTTModel):
    """
    Категории доходов и расходов
    Иерархическая структура с двумя уровнями. Статьи бюджета строятся по категориям их этого справочника.
    Для операции доступен выбор категории только второго уровня.
    Редактируется только из админки.
    ВАЖНО!!! Нужно соблюдать правила редактирования списка категорий в админке:
    - строго два уровня (не должно быть категорий третьего и далее уровней, не должно быть пустой категории
    первого уровня);
    - статья категории первого уровня должна быть формата "XX." (две цифры и точка, уникальные)
    - статья категории второго уровня должна быть формата "XX.ХХ." (две цифры родительской категории,
    точка две цифры и точка, уникальные);
    - изменять категорию с бюджетными объектами нельзя (можно менять только имя и статью при изменении имени и статьи
    базовой категории в части, относящейся к базовой категории);
    - удалять категорию второго уровня, по которой есть категории с бюджетными объектами, нельзя
    """
    name = models.CharField(max_length=100, null=False, blank=False, verbose_name='Наименование')
    parent = TreeForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children',
                            verbose_name='Родительская категория')
    type = models.CharField(max_length=3, choices=CATEGORY_TYPES, null=False, blank=False, verbose_name='Тип')
    item = models.CharField(max_length=10, default='??', db_index=True, null=False, blank=False, verbose_name='Статья')
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True,
                             verbose_name='Добавивший категорию в систему')
    budget = models.ForeignKey('Budget', on_delete=models.CASCADE, null=True, blank=True,
                               verbose_name='Только для бюджета')
    budget_object = models.ForeignKey('BudgetObject', on_delete=models.CASCADE, null=True, blank=True,
                                      verbose_name='Объект бюджета')
    time_create = models.DateTimeField(auto_now_add=True, verbose_name='Время создания')
    time_update = models.DateTimeField(auto_now=True, verbose_name='Время изменения')

    def __str__(self):
        return self.name
        # return self.item + ' ' + self.name

    def get_absolute_url(self):
        return reverse('category', kwargs={'category_id': self.pk})

    class Meta:
        verbose_name = 'Категория доходов/расходов'
        verbose_name_plural = 'Категории доходов/расходов'
        indexes = (Index(fields=['type', 'item', 'budget'], name='category__type_item_budget_idx'),
                   Index(fields=['budget', 'name'], name='category__budget_name_idx'),
                   )
        constraints = [
            models.UniqueConstraint(fields=['budget', 'name'], name='category__budget_name_unique'),
        ]
        ordering = ['item']

    class MPTTMeta:
        verbose_name = 'Категория доходов/расходов'
        verbose_name_plural = 'Категории доходов/расходов'
        order_insertion_by = ['item']

    @classmethod
    def get_category_with_object(cls, budget, category_id, object_id, user):
        """
        Получение категории с бюджетным объектом, по базовой категории и бюджетному объекту.
        Возвращает найденную существующую категорию, либо вновь созданную.
        :param budget: объект текущего бюджета;
        :param category_id: id базовой категории;
        :param object_id: id бюджетного объекта;
        :param user: текущий пользователь;
        :return: id найденной или созданной категории
        """
        # Не объекта или бюджета
        if not object_id or not budget:
            return category_id

        # Получаем по объекты базовой категории и бюджетного объекта
        try:
            category = Category.objects.get(pk=category_id)
            category_name = category.name
            budget_object = BudgetObject.objects.get(pk=object_id)
            object_name = budget_object.name
        except Exception as e:
            # Не смогли получить категорию или объект
            return category_id

        # Если категория первого уровня, то ее и возвращаем (нельзя иметь категорию с бюджетным объектом 1 уровня)
        if not category.parent:
            return category_id

        # Попытаемся найти существующую категорию с бюджетным объектом
        try:
            category_with_object = Category.objects.get(budget_id=budget.pk,
                                                        name=category_name + ' (' + object_name + ')')
            # Нашли нужную категорию!!!
            return category_with_object.pk
        except Exception as e:
            pass

        # Будем создавать новую категорию по заданным базовой категории и бюджетному объекту
        cat = Category()
        cat.name = category_name + ' (' + object_name + ')'
        cat.parent = category.parent
        cat.type = category.type
        cat.user = user
        cat.budget = budget
        cat.budget_object = budget_object

        # Вычислим буквенный индекс (либо "a" для первого, либо следующий, если для данной базовой категории
        # уже существуют категории с другими бюджетными объектами заданного бюджета
        categories = Category.objects.filter(budget_id=budget.pk,
                                             name__startswith=category_name).order_by('budget', '-item')
        if categories:
            last_item = categories[0].item
            cat.item = category.item + chr(ord(last_item[last_item.rfind('.') + 1:]) + 1)
        else:
            cat.item = category.item + 'a'

        # Сохраним новую категорию с бюджетным объектом
        cat.save()
        return cat.pk

    def get_common_category_id(self):
        """
        Получение базовой категории для данной категории
        """
        try:
            return Category.objects.get(type=self.type, item=self.item[:6]).pk
        except Exception as e:
            return self.pk


class BudgetRegister(models.Model):
    """
    Бюджетные регистры
    Собственно, наполнение бюджета. Здесь содержатся плановые и фактические значения в базовой и дополнительной
    валютах бюджета в разрезе категорий и периодов (месяцев), а также в разрезе проектов.
    Регистр, где не указан проект - это текущий приход/расход. Регистр с проектом, соответственно, проектный.
    Для плана проектных доходов/расходов используется регистр с проектом = 0 (планирование проектных расходов
    предусмотрено одной суммой без разбивки на отдельные проекты)
    """
    budget = models.ForeignKey('Budget', null=False, blank=False, on_delete=models.CASCADE, verbose_name='Бюджет')
    budget_year = models.IntegerField(null=False, blank=False, verbose_name='Год бюджета')
    budget_month = models.IntegerField(choices=MONTHS, null=False, blank=False,
                                       verbose_name='Месяц бюджета')
    category = models.ForeignKey('Category', null=False, blank=False, on_delete=models.CASCADE,
                                 verbose_name='Статья бюджета')
    project = models.ForeignKey('Project', on_delete=models.CASCADE, null=True, blank=True, verbose_name='Проект')
    planned_amount_base_cur_1 = models.DecimalField(default=0.00, null=False, blank=False, max_digits=19,
                                                    decimal_places=2,
                                                    verbose_name='План в основной базовой валюте')
    planned_amount_base_cur_2 = models.DecimalField(default=0.00, null=False, blank=False, max_digits=19,
                                                    decimal_places=2,
                                                    verbose_name='План в дополнительной базовой валюте')
    actual_amount_base_cur_1 = models.DecimalField(default=0.00, null=False, blank=False, max_digits=19,
                                                   decimal_places=2,
                                                   verbose_name='Факт в основной базовой валюте')
    actual_amount_base_cur_2 = models.DecimalField(default=0.00, null=False, blank=False, max_digits=19,
                                                   decimal_places=2,
                                                   verbose_name='Факт в дополнительной базовой валюте')

    class Meta:
        verbose_name = 'Регистр бюджета'
        verbose_name_plural = 'Регистры бюджета'
        indexes = (Index(fields=['budget', 'budget_year', 'budget_month', 'category', 'project'],
                         name='br__bud_year_month_cat_pr_idx'),
                   )
        ordering = ['budget', 'budget_year', 'budget_month', 'category', 'project']

    def __str__(self):
        project_name = 'доход' if self.category.type == 'INC' else 'расход'
        if self.project:
            project_name = 'Доп. ' + project_name + ': ' + str(self.project)
        else:
            project_name = 'Текущий ' + project_name
        return 'Регистр бюджета: ' + str(self.budget) + ' - ' + str(self.budget_year) + ' | ' + \
               str(self.budget_month) + ' | ' + str(self.category) + ' | ' + project_name


