from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils.safestring import mark_safe

from main.utils import ftod

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
