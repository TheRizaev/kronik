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
import logging
import random

logger = logging.getLogger(__name__)

from .gcs_storage import (
    create_user_folder_structure,
    upload_video,
    upload_thumbnail,
    list_user_videos,
    get_video_metadata,
    generate_video_url,
    delete_video,
    get_bucket,
    BUCKET_NAME,
    get_user_profile_from_gcs  # Import this to check current profile before updating
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
        
        # Создаем временную директорию, если она не существует
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Получаем имя пользователя для хранения в GCS (сохраняем префикс @)
        username = request.user.username
        # ВАЖНО: больше не удаляем префикс @, сохраняем его для GCS
        
        # Временно сохраняем файлы на сервере
        temp_video_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{video_file.name}")
        
        with open(temp_video_path, 'wb+') as destination:
            for chunk in video_file.chunks():
                destination.write(chunk)
        
        # Загружаем видео в GCS
        video_id = upload_video(
            user_id=username,
            video_file_path=temp_video_path,
            title=title,
            description=description
        )
        
        # Если загрузка видео не удалась
        if not video_id:
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            return JsonResponse({'error': 'Не удалось загрузить видео в Google Cloud Storage'}, status=500)
        
        # Если есть миниатюра, загружаем и её
        thumbnail_url = None
        if thumbnail:
            temp_thumbnail_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{thumbnail.name}")
            with open(temp_thumbnail_path, 'wb+') as destination:
                for chunk in thumbnail.chunks():
                    destination.write(chunk)
            
            thumbnail_success = upload_thumbnail(username, video_id, temp_thumbnail_path)
            
            # Удаляем временный файл миниатюры
            if os.path.exists(temp_thumbnail_path):
                os.remove(temp_thumbnail_path)
                
            if thumbnail_success:
                # Получаем URL миниатюры
                metadata = get_video_metadata(username, video_id)
                if metadata and "thumbnail_path" in metadata:
                    thumbnail_url = generate_video_url(
                        username, 
                        video_id, 
                        file_path=metadata["thumbnail_path"], 
                        expiration_time=3600
                    )
        
        # Удаляем временный файл видео
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        
        # Получаем метаданные для загруженного видео
        video_metadata = get_video_metadata(username, video_id)
        
        # Генерируем временный URL для доступа к видео
        video_url = generate_video_url(username, video_id, expiration_time=3600)
        
        # Добавляем URL в метаданные
        if video_metadata:
            video_metadata['url'] = video_url
            if thumbnail_url:
                video_metadata['thumbnail_url'] = thumbnail_url
                
            # Создаем или обновляем объект Video в базе данных, если необходимо
            try:
                # Если есть категория
                category = None
                if category_id:
                    try:
                        category = Category.objects.get(id=category_id)
                    except Category.DoesNotExist:
                        pass
                
                # Проверяем, существует ли уже видео
                video_obj, created = Video.objects.get_or_create(
                    title=title,
                    defaults={
                        'channel_id': 1,  # Предполагаем, что канал уже создан
                        'category': category,
                        'views': '0',
                        'age_text': 'Только что',
                        'duration': video_metadata.get('duration', '00:00'),
                    }
                )
                
                video_metadata['video_db_id'] = video_obj.id
            except Exception as db_err:
                logger.error(f"Error creating database record: {db_err}")
                # Не возвращаем ошибку, так как видео уже загружено в GCS
        
        return JsonResponse({
            'success': True,
            'video_id': video_id,
            'metadata': video_metadata
        })
        
    except Exception as e:
        logger.error(f"Error uploading video: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def list_videos_from_gcs(request):
    """
    Получает список видео пользователя из GCS с улучшенной обработкой и проверкой миниатюр
    """
    try:
        username = request.user.username
        # ВАЖНО: больше не удаляем префикс @, сохраняем его для GCS
            
        videos = list_user_videos(username)
        
        # Добавляем временные URL для каждого видео
        for video in videos:
            video_id = video.get('video_id')
            if video_id:
                video['url'] = generate_video_url(username, video_id, expiration_time=3600)
                
                # Более надежная проверка наличия миниатюры
                if 'thumbnail_path' in video and video['thumbnail_path']:
                    try:
                        # Проверяем существование блоба миниатюры
                        bucket = get_bucket()
                        if bucket:
                            thumbnail_blob = bucket.blob(video['thumbnail_path'])
                            if thumbnail_blob.exists():
                                video['thumbnail_url'] = generate_video_url(
                                    username, 
                                    video_id, 
                                    file_path=video['thumbnail_path'], 
                                    expiration_time=3600
                                )
                                logger.info(f"Generated thumbnail URL for video {video_id}: {video['thumbnail_url']}")
                            else:
                                logger.warning(f"Thumbnail blob does not exist for video {video_id}: {video['thumbnail_path']}")
                    except Exception as thumb_err:
                        logger.error(f"Error checking thumbnail for video {video_id}: {thumb_err}")
        
        return JsonResponse({
            'success': True,
            'videos': videos
        })
        
    except Exception as e:
        logger.error(f"Error getting video list: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def list_all_videos_from_gcs(request):
    """
    Получает список всех видео из GCS от всех пользователей
    """
    try:
        # Импортируем необходимые функции
        from .gcs_storage import list_user_videos, get_bucket, BUCKET_NAME, generate_video_url, get_user_profile_from_gcs
        import random
        from datetime import datetime
        
        # Получаем бакет
        bucket = get_bucket(BUCKET_NAME)
        if not bucket:
            logger.error("Failed to get bucket")
            return JsonResponse({'error': 'Could not get bucket'}, status=500)
            
        # Получаем список пользователей (папок в GCS)
        blobs = bucket.list_blobs(delimiter='/')
        prefixes = list(blobs.prefixes)
        users = [prefix.replace('/', '') for prefix in prefixes]
        
        logger.info(f"Found users: {users}")
        
        # Собираем видео от всех пользователей
        all_videos = []
        
        # Сохраняем профили пользователей для получения display_name
        user_profiles = {}
        
        for user in users:
            # Получаем профиль пользователя для display_name
            user_profile = get_user_profile_from_gcs(user)
            if user_profile:
                user_profiles[user] = user_profile
            
            # Получаем видео пользователя
            user_videos = list_user_videos(user)
            logger.info(f"User {user} has {len(user_videos)} videos")
            
            if user_videos:
                for video in user_videos:
                    # Добавляем user_id к каждому видео
                    if 'user_id' not in video:
                        video['user_id'] = user
                    
                    # Добавляем display_name автора
                    if user in user_profiles and user_profiles[user] and 'display_name' in user_profiles[user]:
                        video['display_name'] = user_profiles[user]['display_name']
                    else:
                        video['display_name'] = user.replace('@', '')
                        
                    # Генерируем URL для видео
                    video_id = video.get('video_id')
                    if video_id:
                        video['url'] = generate_video_url(user, video_id, expiration_time=3600)
                        
                        # Генерируем URL для миниатюры
                        if 'thumbnail_path' in video and video['thumbnail_path']:
                            try:
                                thumbnail_blob = bucket.blob(video['thumbnail_path'])
                                if thumbnail_blob.exists():
                                    video['thumbnail_url'] = generate_video_url(
                                        user,
                                        video_id,
                                        file_path=video['thumbnail_path'],
                                        expiration_time=3600
                                    )
                            except Exception as thumb_err:
                                logger.error(f"Error checking thumbnail for video {video_id}: {thumb_err}")
                    
                    # Форматируем данные для отображения
                    if 'channel' not in video:
                        video['channel'] = video.get('display_name', video.get('user_id', ''))
                    
                    # Форматируем количество просмотров
                    views = video.get('views', 0)
                    if isinstance(views, int) or (isinstance(views, str) and views.isdigit()):
                        views = int(views)
                        if views >= 1000:
                            video['views_formatted'] = f"{views // 1000}K просмотров"
                        else:
                            video['views_formatted'] = f"{views} просмотров"
                    else:
                        video['views_formatted'] = "0 просмотров"
                    
                    # Форматируем дату загрузки
                    upload_date = video.get('upload_date', '')
                    if upload_date:
                        try:
                            # Преобразуем ISO формат в объект datetime
                            upload_datetime = datetime.fromisoformat(upload_date)
                            # Выводим только дату
                            video['upload_date_formatted'] = upload_datetime.strftime("%d.%m.%Y")
                        except Exception:
                            video['upload_date_formatted'] = upload_date[:10]
                    
                    all_videos.append(video)
        
        # Перемешиваем видео для случайного порядка
        random.shuffle(all_videos)
        
        logger.info(f"Returning {len(all_videos)} videos from all users")
        
        return JsonResponse({
            'success': True,
            'videos': all_videos
        })
        
    except Exception as e:
        logger.error(f"Error getting all videos list: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

# Улучшенная функция для генерации URL
def generate_video_url(user_id, video_id, file_path=None, expiration_time=3600):
    """
    Улучшенная версия для генерации временных URL
    """
    from .gcs_storage import get_bucket, get_video_metadata
    
    try:
        bucket = get_bucket()
        if not bucket:
            logger.error("Failed to get bucket")
            return None
            
        # Если указан конкретный путь к файлу (например, для миниатюры)
        if file_path:
            blob = bucket.blob(file_path)
            if not blob.exists():
                logger.error(f"File not found at path: {file_path}")
                return None
        else:
            # Получаем путь к файлу видео из метаданных
            metadata = get_video_metadata(user_id, video_id)
            if not metadata or "file_path" not in metadata:
                logger.error(f"Could not find information about video {video_id}")
                return None
            
            blob = bucket.blob(metadata["file_path"])
            if not blob.exists():
                logger.error(f"Video file not found in storage")
                return None
        
        # Генерируем URL
        url = blob.generate_signed_url(
            version="v4",
            expiration=expiration_time,
            method="GET"
        )
        
        return url
    
    except Exception as e:
        logger.error(f"Error generating URL: {e}")
        return None

@login_required
def studio_view(request):
    """
    Представление для страницы студии с исправленной обработкой миниатюр
    """
    # Проверяем, является ли пользователь автором
    if not request.user.profile.is_author:
        messages.error(request, 'У вас нет доступа к Студии. Вы должны стать автором, чтобы получить доступ.')
        return redirect('become_author')
    
    # Получаем видео пользователя из GCS
    username = request.user.username
    
    try:
        # Получаем видео пользователя
        videos = list_user_videos(username)
        
        # Создаем URL для каждого видео и его миниатюры
        for video in videos:
            video_id = video.get('video_id')
            if video_id:
                # Генерируем URL для самого видео
                video['url'] = generate_video_url(username, video_id, expiration_time=3600)
                
                # Более надежная проверка наличия миниатюры
                if 'thumbnail_path' in video and video['thumbnail_path']:
                    try:
                        # Получаем доступ к бакету
                        bucket = get_bucket()
                        if bucket:
                            # Проверяем существование файла миниатюры в GCS
                            thumbnail_blob = bucket.blob(video['thumbnail_path'])
                            
                            if thumbnail_blob.exists():
                                # Генерируем URL для миниатюры
                                video['thumbnail_url'] = generate_video_url(
                                    username, 
                                    video_id, 
                                    file_path=video['thumbnail_path'], 
                                    expiration_time=3600
                                )
                                logger.info(f"Миниатюра найдена для видео {video_id}: {video['thumbnail_url']}")
                            else:
                                logger.warning(f"Миниатюра не найдена в GCS: {video['thumbnail_path']}")
                    except Exception as e:
                        logger.error(f"Ошибка при проверке миниатюры для видео {video_id}: {e}")
        
        # Debug сообщение
        logger.info(f"Загружено {len(videos)} видео из GCS для пользователя {username}")
        for i, v in enumerate(videos):
            logger.info(f"Видео {i+1}: ID={v.get('video_id')}, Миниатюра={v.get('thumbnail_url', 'Отсутствует')}")
        
        # Получаем категории для формы загрузки
        categories = Category.objects.all()
        
        return render(request, 'studio/studio.html', {
            'videos': videos,
            'categories': categories
        })
    except Exception as e:
        messages.error(request, f'Ошибка при получении данных: {e}')
        logger.error(f"Ошибка в studio_view: {e}")
        
    return render(request, 'studio/studio.html', {
        'videos': []
    })
    
@login_required
@require_http_methods(["DELETE"])
def delete_video_from_gcs(request, video_id):
    """
    Удаляет видео из GCS
    """
    try:
        username = request.user.username
        # ВАЖНО: больше не удаляем префикс @, сохраняем его для GCS
            
        success = delete_video(username, video_id)
        
        if success:
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'error': 'Не удалось удалить видео'}, status=400)
            
    except Exception as e:
        logger.error(f"Error deleting video: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["GET"])
def get_video_url(request, video_id):
    """
    Получает временный URL для видео
    """
    try:
        username = request.user.username
        # ВАЖНО: больше не удаляем префикс @, сохраняем его для GCS
            
        url = generate_video_url(username, video_id, expiration_time=3600)
        
        if url:
            return JsonResponse({
                'success': True,
                'url': url
            })
        else:
            return JsonResponse({'error': 'Не удалось сгенерировать URL'}, status=400)
            
    except Exception as e:
        logger.error(f"Error generating URL: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)