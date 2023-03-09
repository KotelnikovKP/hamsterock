# Generated by Django 4.1.7 on 2023-03-09 11:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0002_currencyrate_account_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccountTurnover',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('budget_period', models.DateTimeField(verbose_name='Период бюджета')),
                ('begin_balance_base_cur_1', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Остаток на начало периода в базовой валюте')),
                ('credit_turnover_base_cur_1', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Кредитовый оборот в базовой валюте')),
                ('debit_turnover_base_cur_1', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Дебетовый оборот в базовой валюте')),
                ('end_balance_base_cur_1', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Остаток на конец периода в базовой валюте')),
                ('begin_balance_base_cur_2', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Остаток на начало периода в дополнительной валюте')),
                ('credit_turnover_base_cur_2', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Кредитовый оборот в дополнительной валюте')),
                ('debit_turnover_base_cur_2', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Дебетовый оборот в дополнительной валюте')),
                ('end_balance_base_cur_2', models.DecimalField(decimal_places=2, default=0.0, max_digits=19, verbose_name='Остаток на конец периода в дополнительной валюте')),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='main.account', verbose_name='Счет/кошелек')),
                ('budget', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='main.budget', verbose_name='Бюджет')),
            ],
            options={
                'verbose_name': 'Бюджетные обороты по счету',
                'verbose_name_plural': 'Бюджетные обороты по счету',
                'ordering': ['budget', 'account', 'budget_period'],
            },
        ),
        migrations.AddIndex(
            model_name='accountturnover',
            index=models.Index(fields=['budget', 'account', 'budget_period'], name='at__budget_account_period_idx'),
        ),
    ]