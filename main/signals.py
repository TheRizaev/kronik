from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile
from django.conf import settings
import os
import shutil
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    """Create a UserProfile for each new User and set default avatar."""
    if created:
        # Создаем профиль
        profile = UserProfile.objects.create(user=instance)
        
        # Пытаемся установить аватар по умолчанию
        try:
            # Путь к дефолтному изображению
            default_avatar_path = os.path.join(settings.STATIC_ROOT, 'default.png')
            
            # Если дефолтного изображения нет в STATIC_ROOT, ищем в директории static
            if not os.path.exists(default_avatar_path):
                default_avatar_path = os.path.join(settings.BASE_DIR, 'static', 'default.png')
            
            # Проверяем существование файла
            if os.path.exists(default_avatar_path):
                # Путь куда сохранить аватар пользователя
                media_dir = os.path.join(settings.MEDIA_ROOT, 'profile_pics')
                os.makedirs(media_dir, exist_ok=True)
                
                # Генерируем файл для пользователя
                user_avatar_path = os.path.join(media_dir, f"avatar_{instance.id}.png")
                
                # Копируем дефолтное изображение как аватар пользователя
                shutil.copy(default_avatar_path, user_avatar_path)
                
                # Устанавливаем относительный путь в профиле
                rel_path = os.path.join('profile_pics', f"avatar_{instance.id}.png")
                profile.profile_picture = rel_path
                profile.save()
                
                logger.info(f"Default avatar set for user {instance.username}")
            else:
                logger.warning(f"Default avatar file not found at {default_avatar_path}")
        except Exception as e:
            logger.error(f"Error setting default avatar: {e}")

@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    """Save the UserProfile when the User is updated."""
    if hasattr(instance, 'profile'):
        instance.profile.save()