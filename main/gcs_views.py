from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from .models import Category, Video
from django.views.decorators.http import require_http_methods
from django.conf import settings
import os
import json
from datetime import datetime
import uuid
import tempfile

# Импортируем GCS модуль из нашего файла
from .gcs_storage import (
    create_user_folder_structure,
    upload_video,
    upload_thumbnail,
    list_user_videos,
    get_video_metadata,
    generate_video_url,
    delete_video
)

@login_required
@require_http_methods(["POST"])
def upload_video_to_gcs(request):
    """
    Обработчик загрузки видео в Google Cloud Storage с улучшенной обработкой ошибок
    """
    try:
        # Получаем файлы и данные из запроса
        video_file = request.FILES.get('video_file')
        thumbnail = request.FILES.get('thumbnail')
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        category_id = request.POST.get('category')
        
        if not video_file or not title:
            return JsonResponse({'error': 'Видео и название обязательны'}, status=400)
        
        # Создаем временную директорию, если ее нет
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Сохраняем файлы временно на сервере
        user_id = f"user_{request.user.id}"
        temp_video_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{video_file.name}")
        
        with open(temp_video_path, 'wb+') as destination:
            for chunk in video_file.chunks():
                destination.write(chunk)
        
        # Загружаем видео в GCS
        video_id = upload_video(
            user_id=user_id,
            video_file_path=temp_video_path,
            title=title,
            description=description
        )
        
        # Если загрузка видео не удалась
        if not video_id:
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            return JsonResponse({'error': 'Не удалось загрузить видео в Google Cloud Storage'}, status=500)
        
        # Если есть превью, загружаем его тоже
        thumbnail_url = None
        if thumbnail:
            temp_thumbnail_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{thumbnail.name}")
            with open(temp_thumbnail_path, 'wb+') as destination:
                for chunk in thumbnail.chunks():
                    destination.write(chunk)
            
            thumbnail_success = upload_thumbnail(user_id, video_id, temp_thumbnail_path)
            
            # Удаляем временный файл превью
            if os.path.exists(temp_thumbnail_path):
                os.remove(temp_thumbnail_path)
                
            if thumbnail_success:
                # Получаем ссылку на миниатюру
                metadata = get_video_metadata(user_id, video_id)
                if metadata and "thumbnail_path" in metadata:
                    thumbnail_url = generate_video_url(
                        user_id, 
                        video_id, 
                        file_path=metadata["thumbnail_path"], 
                        expiration_time=3600
                    )
        
        # Удаляем временный файл видео
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        
        # Получаем метаданные загруженного видео
        video_metadata = get_video_metadata(user_id, video_id)
        
        # Генерируем временную ссылку для доступа к видео
        video_url = generate_video_url(user_id, video_id, expiration_time=3600)
        
        # Добавляем URL к метаданным
        if video_metadata:
            video_metadata['url'] = video_url
            if thumbnail_url:
                video_metadata['thumbnail_url'] = thumbnail_url
                
            # Создаем или обновляем объект Video в базе данных, если необходимо
            try:
                # Если используется категория
                category = None
                if category_id:
                    try:
                        category = Category.objects.get(id=category_id)
                    except Category.DoesNotExist:
                        pass
                
                # Проверяем, существует ли такое видео
                video_obj, created = Video.objects.get_or_create(
                    title=title,
                    defaults={
                        'channel_id': 1,  # Предполагается что канал уже создан
                        'category': category,
                        'views': '0',
                        'age_text': 'Только что',
                        'duration': video_metadata.get('duration', '00:00'),
                    }
                )
                
                video_metadata['video_db_id'] = video_obj.id
            except Exception as db_err:
                print(f"Ошибка при создании записи в БД: {db_err}")
                # Не возвращаем ошибку, так как видео уже загружено в GCS
        
        return JsonResponse({
            'success': True,
            'video_id': video_id,
            'metadata': video_metadata
        })
        
    except Exception as e:
        print(f"Ошибка при загрузке видео: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def list_videos_from_gcs(request):
    """
    Получение списка видео пользователя из GCS с улучшенной обработкой
    """
    try:
        user_id = f"user_{request.user.id}"
        videos = list_user_videos(user_id)
        
        # Добавляем временные URL к каждому видео
        for video in videos:
            video_id = video.get('video_id')
            if video_id:
                # URL для видео
                video['url'] = generate_video_url(user_id, video_id, expiration_time=3600)
                
                # URL для миниатюры, если она есть
                if 'thumbnail_path' in video:
                    video['thumbnail_url'] = generate_video_url(
                        user_id, 
                        video_id, 
                        file_path=video['thumbnail_path'], 
                        expiration_time=3600
                    )
        
        return JsonResponse({
            'success': True,
            'videos': videos
        })
        
    except Exception as e:
        print(f"Ошибка при получении списка видео: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

# Исправленная версия функции для генерации URL
def generate_video_url(user_id, video_id, file_path=None, expiration_time=3600):
    """
    Улучшенная версия для генерации временных URL
    """
    from .gcs_storage import get_bucket, get_video_metadata
    
    try:
        bucket = get_bucket()
        
        # Если указан конкретный путь к файлу (например, к миниатюре)
        if file_path:
            blob = bucket.blob(file_path)
            if not blob.exists():
                print(f"Файл не найден по пути: {file_path}")
                return None
        else:
            # Получаем путь к видеофайлу из метаданных
            metadata = get_video_metadata(user_id, video_id)
            if not metadata or "file_path" not in metadata:
                print(f"Не удалось найти информацию о видео {video_id}")
                return None
            
            blob = bucket.blob(metadata["file_path"])
            if not blob.exists():
                print(f"Видеофайл не найден в хранилище")
                return None
        
        # Генерируем URL
        url = blob.generate_signed_url(
            version="v4",
            expiration=expiration_time,
            method="GET"
        )
        
        return url
    
    except Exception as e:
        print(f"Ошибка при генерации ссылки: {e}")
        return None

@login_required
def studio_view(request):
    """
    View для страницы студии с интеграцией GCS
    """
    # Проверяем, является ли пользователь автором
    if not request.user.profile.is_author:
        messages.error(request, 'У вас нет доступа к Студии. Вы должны стать автором, чтобы получить доступ.')
        return redirect('become_author')
    
    # Получаем список видео пользователя из GCS
    user_id = f"user_{request.user.id}"
    
    try:
        # Импортируем функции GCS
        from .gcs_storage import create_user_folder_structure, list_user_videos
        
        # Создаем структуру папок пользователя, если она не существует
        create_user_folder_structure(user_id)
        
        # Получаем список видео пользователя
        videos = list_user_videos(user_id)
        
        # Получаем список категорий для формы загрузки
        categories = Category.objects.all()
        
        return render(request, 'studio/studio.html', {
            'videos': videos,
            'categories': categories
        })
    except Exception as e:
        messages.error(request, f'Ошибка при получении данных: {e}')
        videos = []
        
    return render(request, 'studio/studio.html', {
        'videos': []
    })
    
@login_required
@require_http_methods(["DELETE"])
def delete_video_from_gcs(request, video_id):
    """
    Удаление видео из GCS
    """
    try:
        user_id = f"user_{request.user.id}"
        from .gcs_storage import delete_video
        
        success = delete_video(user_id, video_id)
        
        if success:
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'error': 'Не удалось удалить видео'}, status=400)
            
    except Exception as e:
        print(f"Ошибка при удалении видео: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["GET"])
def get_video_url(request, video_id):
    """
    Получение временной ссылки на видео
    """
    try:
        user_id = f"user_{request.user.id}"
        from .gcs_storage import generate_video_url
        
        url = generate_video_url(user_id, video_id, expiration_time=3600)
        
        if url:
            return JsonResponse({
                'success': True,
                'url': url
            })
        else:
            return JsonResponse({'error': 'Не удалось сгенерировать ссылку'}, status=400)
            
    except Exception as e:
        print(f"Ошибка при генерации ссылки: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)