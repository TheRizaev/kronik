
from django.apps import AppConfig

class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'
    
    def ready(self):
        import main.signals  # Import signals module to register user profile signals
        import main.gcs_utils  # Import GCS utils to register GCS folder creation signals