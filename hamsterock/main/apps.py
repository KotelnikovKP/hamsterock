from django.apps import AppConfig


class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'
    verbose_name = 'Хомячок - управление личным бюджетом'

    def ready(self):
        import main.signals
