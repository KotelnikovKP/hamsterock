# Generated by Django 4.1.7 on 2023-03-10 05:46

from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('main', '0004_budgetobject_project_category_budgetregister_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[(None, '<тип не выбран>'), ('CRE', 'Приход'), ('DEB', 'Расход'), ('MO+', 'Перемещение приход'), ('MO-', 'Перемещение расход')], max_length=3, verbose_name='Тип')),
                ('time_transaction', models.DateTimeField(verbose_name='Дата-время операции')),
                ('time_zone', models.DecimalField(choices=[(Decimal('-12.00'), '(UTC-12:00) Линия перемены дат'), (Decimal('-11.00'), '(UTC-11:00) Время в формате UTC -11'), (Decimal('-10.00'), '(UTC-10:00) Гавайи'), (Decimal('-9.00'), '(UTC-09:00) Аляска'), (Decimal('-8.00'), '(UTC-08:00) Тихоокеанское время (США и Канада)'), (Decimal('-7.00'), '(UTC-07:00) Горное время (США и Канада)'), (Decimal('-6.00'), '(UTC-06:00) Центральное время (США и Канада), Мехико'), (Decimal('-5.00'), '(UTC-05:00) Восточное время (США и Канада), Богота, Лима'), (Decimal('-4.00'), '(UTC-04:00) Атлантическое время (Канада), Каракас, Ла-Пас'), (Decimal('-3.50'), '(UTC-03:30) Ньюфаундленд'), (Decimal('-3.00'), '(UTC-03:00) Бразилиа, Буэнос-Айрес'), (Decimal('-2.00'), '(UTC-02:00) Время в формате UTC -02'), (Decimal('-1.00'), '(UTC-01:00) Азорские острова'), (Decimal('0.00'), '(UTC) Время Западной Европы, Дублин, Эдинбург, Лиссабон, Лондон'), (Decimal('1.00'), '(UTC+01:00) Амстердам, Берлин, Брюссель, Копенгаген, Мадрид, Париж, Рим'), (Decimal('2.00'), '(UTC+02:00) Вильнюс, Иерусалим, Каир, Калининград, Киев, Рига, Таллин, Хельсинки'), (Decimal('3.00'), '(UTC+03:00) Багдад, Минск, Москва, Санкт-Петербург, Стамбул'), (Decimal('3.50'), '(UTC+03:30) Тегеран'), (Decimal('4.00'), '(UTC+04:00) Абу-Даби, Баку, Ереван, Самара, Тбилиси'), (Decimal('4.50'), '(UTC+04:30) Кабул'), (Decimal('5.00'), '(UTC+05:00) Ашхабад, Душанбе, Екатеринбург, Исламабад, Ташкент'), (Decimal('5.50'), '(UTC+05:30) Колката, Мумбаи, Нью-Дели, Ченнай'), (Decimal('5.75'), '(UTC+05:45) Катманду'), (Decimal('6.00'), '(UTC+06:00) Алматы, Астана, Дакка, Омск'), (Decimal('7.00'), '(UTC+07:00) Бангкок, Джакарта, Красноярск, Новосибирск, Томск, Ханой'), (Decimal('8.00'), '(UTC+08:00) Гонконг, Иркутск, Пекин, Улан-Батор, Урумчи, Чунцин'), (Decimal('9.00'), '(UTC+09:00) Осака, Пхеньян, Саппоро, Сеул, Токио, Якутск'), (Decimal('9.50'), '(UTC+09:30) Аделаида, Дарвин'), (Decimal('10.00'), '(UTC+10:00) Владивосток, Канберра, Мельбурн, Сидней'), (Decimal('11.00'), '(UTC+11:00) Магадан, Сахалин, Соломоновы о-ва, Новая Каледония'), (Decimal('12.00'), '(UTC+12:00) Веллингтон, Окленд, Петропавловск-Камчатский, Фиджи')], decimal_places=2, default=0.0, max_digits=5, verbose_name='Часовой пояс времени операций')),
                ('amount_acc_cur', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Сумма операции в валюте счета')),
                ('amount', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Сумма операции')),
                ('budget_year', models.IntegerField(verbose_name='Год периода бюджета')),
                ('budget_month', models.IntegerField(choices=[(None, '<не выбран>'), (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'), (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'), (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')], verbose_name='Месяц периода бюджета')),
                ('place', models.CharField(blank=True, max_length=255, null=True, verbose_name='Место совершения операции')),
                ('description', models.CharField(blank=True, max_length=255, null=True, verbose_name='Описание операции')),
                ('mcc_code', models.CharField(blank=True, max_length=4, null=True, verbose_name='MCC код от банка')),
                ('banks_category', models.CharField(blank=True, max_length=255, null=True, verbose_name='Категория операции от банка')),
                ('banks_description', models.CharField(blank=True, max_length=255, null=True, verbose_name='Описание операции от банка')),
                ('time_create', models.DateTimeField(auto_now_add=True, verbose_name='Время создания')),
                ('time_update', models.DateTimeField(auto_now=True, verbose_name='Время изменения')),
                ('balance_acc_cur', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Остаток на счете в валюте счета')),
                ('rate_base_cur_1', models.DecimalField(decimal_places=9, default=0.0, max_digits=19, verbose_name='Курс основной базовой валюты')),
                ('amount_base_cur_1', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Сумма операции в основной базовой валюте')),
                ('balance_base_cur_1', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Остаток на счете в основной базовой валюте')),
                ('rate_base_cur_2', models.DecimalField(decimal_places=9, default=0.0, max_digits=19, verbose_name='Курс дополнительной базовой валюты')),
                ('amount_base_cur_2', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Сумма операции в дополнительной базовой валюте')),
                ('balance_base_cur_2', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Остаток на счете в дополнительной базовой валюте')),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='main.account', verbose_name='Счет/кошелек')),
                ('budget', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='main.budget', verbose_name='Бюджет')),
                ('currency', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='main.currency', verbose_name='Валюта операции')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='main.project', verbose_name='Проект')),
                ('sender', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='receiver', to='main.transaction', verbose_name='Операция-источник')),
                ('user_create', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='user_create', to=settings.AUTH_USER_MODEL, verbose_name='Добавивший операцию в систему')),
                ('user_update', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='user_update', to=settings.AUTH_USER_MODEL, verbose_name='Изменивший операцию в системе')),
            ],
            options={
                'verbose_name': 'Операция',
                'verbose_name_plural': 'Операции',
                'ordering': ['budget', 'account', '-time_transaction'],
            },
        ),
        migrations.CreateModel(
            name='TransactionCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_acc_cur', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Сумма для категории в валюте счета')),
                ('amount_base_cur_1', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Сумма для категории в основной базовой валюте')),
                ('amount_base_cur_2', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Сумма для категории в дополнительной базовой валюте')),
                ('budget_year', models.IntegerField(verbose_name='Год периода бюджета')),
                ('budget_month', models.IntegerField(choices=[(None, '<не выбран>'), (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'), (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'), (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь')], verbose_name='Месяц периода бюджета')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='main.category', verbose_name='Категория')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='main.project', verbose_name='Проект')),
                ('transaction', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transaction_categories', to='main.transaction', verbose_name='Операция')),
            ],
            options={
                'verbose_name': 'Категория операции',
                'verbose_name_plural': 'Категории операций',
                'ordering': ['pk'],
            },
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['budget', 'account', '-time_transaction'], name='t__budget_account_time_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['budget', 'type', '-time_transaction'], name='t__budget_type_time_idx'),
        ),
    ]