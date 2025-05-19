from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from .models import Category, Video, VideoView
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.conf import settings
import os
from .s3_storage import update_video_metadata, upload_video_with_quality_processing, get_video_metadata, upload_thumbnail, generate_video_url, get_video_url_with_quality, BUCKET_NAME, cache_video_metadata
import uuid
import logging
logger = logging.getLogger(__name__)

from .s3_storage import (
    create_user_folder_structure,
    upload_video,
    upload_thumbnail,
    get_video_metadata,
    generate_video_url,
    delete_video,
    get_bucket,
    BUCKET_NAME,
    get_user_profile_from_gcs
)

@login_required
@require_http_methods(["POST"])
def upload_video_to_gcs(request):
    """
    Handler for uploading videos to Google Cloud Storage with quality processing
    """
    try:
        # Get files and data from request
        video_file = request.FILES.get('video_file')
        thumbnail = request.FILES.get('thumbnail')
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        category_id = request.POST.get('category')
        process_qualities = request.POST.get('process_qualities', 'true').lower() == 'true'
        
        if not video_file or not title:
            return JsonResponse({'error': 'Video and title are required'}, status=400)
        
        # Create temp directory if it doesn't exist
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Get username for GCS storage (preserve @ prefix)
        username = request.user.username
        user_id = f"@{username}" if not username.startswith('@') else username
        
        # Temporarily save video file on server
        temp_video_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{video_file.name}")
        with open(temp_video_path, 'wb+') as destination:
            for chunk in video_file.chunks():
                destination.write(chunk)
        
        # Upload video to GCS with quality processing directly
        video_id = upload_video_with_quality_processing(
            user_id=user_id,
            video_file_path=temp_video_path,
            title=title,
            description=description,
            process_qualities=process_qualities  # This will handle quality processing synchronously
        )
        
        # If video upload failed
        if not video_id:
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            return JsonResponse({'error': 'Failed to upload video to Google Cloud Storage'}, status=500)
        
        # Get the GCS path of the uploaded video
        metadata = get_video_metadata(user_id, video_id)
        if not metadata or 'file_path' not in metadata:
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            return JsonResponse({'error': 'Failed to retrieve video metadata'}, status=500)
        
        # Handle thumbnail if present
        thumbnail_url = None
        if thumbnail:
            temp_thumbnail_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{thumbnail.name}")
            with open(temp_thumbnail_path, 'wb+') as destination:
                for chunk in thumbnail.chunks():
                    destination.write(chunk)
            
            thumbnail_success = upload_thumbnail(user_id, video_id, temp_thumbnail_path)
            
            if os.path.exists(temp_thumbnail_path):
                os.remove(temp_thumbnail_path)
                
            if thumbnail_success:
                metadata = get_video_metadata(user_id, video_id)
                if metadata and "thumbnail_path" in metadata:
                    thumbnail_url = generate_video_url(
                        user_id, 
                        video_id, 
                        file_path=metadata["thumbnail_path"], 
                        expiration_time=3600
                    )
        
        # Delete temp video file
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        
        # Get updated metadata for uploaded video
        video_metadata = get_video_metadata(user_id, video_id)
        
        # Generate temporary URL for video access
        video_url_info = get_video_url_with_quality(user_id, video_id, expiration_time=3600)
        
        # Add URL to metadata
        if video_metadata:
            if video_url_info:
                video_metadata['url'] = video_url_info['url']
                video_metadata['quality'] = video_url_info['quality']
                video_metadata['available_qualities'] = video_url_info['available_qualities']
            
            if thumbnail_url:
                video_metadata['thumbnail_url'] = thumbnail_url
                
            # Create or update Video object in database
            try:
                category = None
                if category_id:
                    try:
                        category = Category.objects.get(id=category_id)
                    except Category.DoesNotExist:
                        pass
                
                video_obj, created = Video.objects.get_or_create(
                    title=title,
                    defaults={
                        'channel_id': 1,  # Assume channel already created
                        'category': category,
                        'views': '0',
                        'age_text': 'Just now',
                        'duration': video_metadata.get('duration', '00:00'),
                    }
                )
                
                video_metadata['video_db_id'] = video_obj.id
            except Exception as db_err:
                logger.error(f"Error creating database record: {db_err}")
        
        return JsonResponse({
            'success': True,
            'video_id': video_id,
            'metadata': video_metadata,
            'processing_qualities': process_qualities
        })
        
    except Exception as e:
        logger.error(f"Error uploading video: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


def list_all_videos(request):
    """
    Fixed function to retrieve videos list from S3.
    Always adds 'channel' field to prevent template errors.
    """
    try:
        from .s3_storage import get_bucket, BUCKET_NAME, generate_video_url
        import logging
        import json
        from datetime import datetime
        
        logger = logging.getLogger(__name__)
        
        logger.info("Starting list_all_videos API request")
        
        # Parse pagination parameters
        try:
            offset = int(request.GET.get('offset', 0))
        except (ValueError, TypeError):
            offset = 0
            
        try:
            limit = int(request.GET.get('limit', 20))
        except (ValueError, TypeError):
            limit = 20
            
        only_metadata = request.GET.get('only_metadata', 'false').lower() == 'true'
        
        # Get bucket
        bucket = get_bucket(BUCKET_NAME)
        if not bucket:
            logger.error("Failed to get bucket")
            return JsonResponse({'error': 'Failed to access storage', 'success': False}, status=500)
        
        client = bucket['client']
        bucket_name = bucket['name']
        
        # Get list of users from S3
        users = set()
        
        # List objects with delimiter to get "directories"
        result = client.list_objects_v2(Bucket=bucket_name, Delimiter='/')
        
        # Get all prefixes (folders)
        for prefix in result.get('CommonPrefixes', []):
            user_id = prefix.get('Prefix', '').rstrip('/')
            if user_id and user_id.startswith('@'):
                users.add(user_id)
        
        logger.info(f"Found {len(users)} users in S3")
        
        # Collect all videos
        all_videos = []
        
        for user_id in users:
            try:
                # Look for metadata folder
                metadata_prefix = f"{user_id}/metadata/"
                
                # List objects with the metadata prefix
                paginator = client.get_paginator('list_objects_v2')
                metadata_objects = []
                
                # List objects with the metadata prefix
                pages = paginator.paginate(Bucket=bucket_name, Prefix=metadata_prefix)
                for page in pages:
                    if 'Contents' in page:
                        metadata_objects.extend(page['Contents'])
                
                # Get user profile for display name
                user_profile = None
                try:
                    user_meta_key = f"{user_id}/bio/user_meta.json"
                    response = client.get_object(Bucket=bucket_name, Key=user_meta_key)
                    user_profile = json.loads(response['Body'].read().decode('utf-8'))
                except Exception as profile_error:
                    logger.error(f"Error loading profile for {user_id}: {profile_error}")
                    user_profile = None
                
                # Process all metadata files for videos
                for obj in metadata_objects:
                    if obj['Key'].endswith('.json'):
                        try:
                            # Get video metadata
                            response = client.get_object(Bucket=bucket_name, Key=obj['Key'])
                            metadata = json.loads(response['Body'].read().decode('utf-8'))
                            
                            # Add user information
                            metadata['user_id'] = user_id
                            
                            # Add display_name from user profile or fallback
                            if user_profile and 'display_name' in user_profile:
                                metadata['display_name'] = user_profile['display_name']
                            else:
                                metadata['display_name'] = user_id.replace('@', '')
                            
                            # IMPORTANT FIX: Always add 'channel' field to prevent template errors
                            metadata['channel'] = metadata.get('display_name') or user_id.replace('@', '')
                            
                            # Format views
                            views = metadata.get('views', 0)
                            if isinstance(views, (int, str)) and str(views).isdigit():
                                views = int(views)
                                metadata['views_formatted'] = f"{views // 1000}K просмотров" if views >= 1000 else f"{views} просмотров"
                            else:
                                metadata['views_formatted'] = "0 просмотров"
                            
                            # Format upload date
                            upload_date = metadata.get('upload_date', '')
                            if upload_date:
                                try:
                                    upload_datetime = datetime.fromisoformat(upload_date)
                                    metadata['upload_date_formatted'] = upload_datetime.strftime("%d.%m.%Y")
                                except Exception:
                                    metadata['upload_date_formatted'] = upload_date[:10] if upload_date else "Недавно"
                            else:
                                metadata['upload_date_formatted'] = "Недавно"
                            
                            all_videos.append(metadata)
                        except Exception as e:
                            logger.error(f"Error processing metadata for {obj['Key']}: {e}")
            except Exception as e:
                logger.error(f"Error processing user {user_id}: {e}")
        
        # Check if we found any videos
        if not all_videos:
            logger.warning("No videos found in S3")
            # Return empty list
            return JsonResponse({
                'success': True,
                'videos': [],
                'total': 0
            })
        
        # Sort videos by upload date (newest first)
        try:
            all_videos.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
        except Exception as sort_error:
            logger.error(f"Error sorting videos: {sort_error}")
        
        total_videos = len(all_videos)
        
        # Apply pagination
        paginated_videos = all_videos[offset:offset + limit]
        
        # If requesting full data with URLs, generate URLs for videos and thumbnails
        if not only_metadata:
            # Generate URLs for videos and thumbnails
            for video in paginated_videos:
                try:
                    video_id = video.get('video_id')
                    user_id = video.get('user_id')
                    
                    if video_id and user_id:
                        # URL for video
                        video['url'] = generate_video_url(user_id, video_id, expiration_time=3600)
                        
                        # URL for thumbnail
                        if 'thumbnail_path' in video:
                            video['thumbnail_url'] = generate_video_url(
                                user_id, video_id, file_path=video['thumbnail_path'], expiration_time=3600
                            )
                except Exception as url_error:
                    logger.error(f"Error generating URL for video {video.get('video_id')}: {url_error}")
        
        logger.info(f"Returning {len(paginated_videos)} videos from total {total_videos}")
        return JsonResponse({
            'success': True,
            'videos': paginated_videos,
            'total': total_videos
        })
    
    except Exception as e:
        import traceback
        logger.error(f"Error in list_all_videos: {e}")
        logger.error(traceback.format_exc())
        
        return JsonResponse({
            'success': False,
            'error': str(e),
            'videos': []
        }, status=500)

@login_required
@require_http_methods(["GET"])
def list_user_videos(request, username=None):
    """
    Optimized function to retrieve a list of videos for a specific user.
    Only returns metadata and previews, without loading the actual video content.
    """
    try:
        from .s3_storage import get_bucket, BUCKET_NAME, generate_video_url, get_user_profile_from_gcs
        import logging
        import json
        from datetime import datetime
        
        logger = logging.getLogger(__name__)
        
        logger.info("Starting optimized list_user_videos API request")
        
        # If username not provided, use the logged-in user's username
        if not username:
            if not request.user.is_authenticated:
                return JsonResponse({'error': 'Пользователь не авторизован'}, status=401)
            username = request.user.username
        
        # Get parameters from the request
        try:
            offset = int(request.GET.get('offset', 0))
        except (ValueError, TypeError):
            offset = 0
            
        try:
            limit = int(request.GET.get('limit', 20))
        except (ValueError, TypeError):
            limit = 20
            
        only_metadata = request.GET.get('only_metadata', 'false').lower() == 'true'
        
        # Get the S3 bucket
        bucket = get_bucket(BUCKET_NAME)
        if not bucket:
            logger.error(f"Failed to get bucket for user {username}")
            return JsonResponse({'error': 'Не удалось получить доступ к хранилищу'}, status=500)

        client = bucket['client']
        bucket_name = bucket['name']

        # Get user profile for display name
        user_profile = None
        try:
            user_profile = get_user_profile_from_gcs(username)
        except Exception as profile_error:
            logger.error(f"Error loading profile for {username}: {profile_error}")
        
        # Get metadata files for the user
        metadata_prefix = f"{username}/metadata/"
        
        # List objects with the metadata prefix using pagination
        paginator = client.get_paginator('list_objects_v2')
        metadata_objects = []
        
        # Get all metadata objects for this user
        pages = paginator.paginate(Bucket=bucket_name, Prefix=metadata_prefix)
        for page in pages:
            if 'Contents' in page:
                metadata_objects.extend(page['Contents'])
        
        # Process metadata files
        videos = []
        for obj in metadata_objects:
            if obj['Key'].endswith('.json'):
                try:
                    # Get video metadata
                    response = client.get_object(Bucket=bucket_name, Key=obj['Key'])
                    metadata = json.loads(response['Body'].read().decode('utf-8'))
                    
                    # Add user information
                    metadata['user_id'] = username
                    if user_profile:
                        metadata['display_name'] = user_profile.get('display_name', username.replace('@', ''))
                    else:
                        metadata['display_name'] = username.replace('@', '')
                        
                    # Add channel for compatibility with the template
                    metadata['channel'] = metadata.get('display_name', username.replace('@', ''))
                    
                    # Format views
                    views = metadata.get('views', 0)
                    if isinstance(views, (int, str)) and str(views).isdigit():
                        views = int(views)
                        metadata['views_formatted'] = f"{views // 1000}K просмотров" if views >= 1000 else f"{views} просмотров"
                    else:
                        metadata['views_formatted'] = "0 просмотров"
                    
                    # Format upload date
                    upload_date = metadata.get('upload_date', '')
                    if upload_date:
                        try:
                            upload_datetime = datetime.fromisoformat(upload_date)
                            metadata['upload_date_formatted'] = upload_datetime.strftime("%d.%m.%Y")
                        except Exception:
                            metadata['upload_date_formatted'] = upload_date[:10] if upload_date else "Недавно"
                    else:
                        metadata['upload_date_formatted'] = "Недавно"
                    
                    videos.append(metadata)
                except Exception as e:
                    logger.error(f"Error processing metadata for {obj['Key']}: {e}")
        
        # Sort videos by upload date (newest first)
        try:
            videos.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
        except Exception as sort_error:
            logger.error(f"Error sorting videos: {sort_error}")
        
        total_videos = len(videos)
        
        # Apply pagination
        paginated_videos = videos[offset:offset + limit]
        
        # If not requesting only metadata, generate URLs for videos and thumbnails
        if not only_metadata:
            for video in paginated_videos:
                try:
                    video_id = video.get('video_id')
                    
                    if video_id:
                        # URL for video
                        video['url'] = generate_video_url(username, video_id, expiration_time=3600)
                        
                        # URL for thumbnail
                        if 'thumbnail_path' in video:
                            video['thumbnail_url'] = generate_video_url(
                                username, video_id, file_path=video['thumbnail_path'], expiration_time=3600
                            )
                except Exception as url_error:
                    logger.error(f"Error generating URL for video {video.get('video_id')}: {url_error}")
        
        logger.info(f"Returning {len(paginated_videos)} videos for user {username}")
        return JsonResponse({
            'success': True,
            'videos': paginated_videos,
            'total': total_videos
        })
    
    except Exception as e:
        import traceback
        logger.error(f"Error in list_user_videos: {e}")
        logger.error(traceback.format_exc())
        
        return JsonResponse({
            'success': False,
            'error': str(e),
            'videos': []
        }, status=500)        

# Улучшенная функция для генерации URL
def generate_video_url(user_id, video_id, file_path=None, expiration_time=3600):
    """
    Улучшенная версия для генерации временных URL
    """
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
    Fast-loading view for the studio page that shows placeholders immediately,
    similar to how index.html works.
    """
    # Check if the user is an author
    if not request.user.profile.is_author:
        messages.error(request, 'У вас нет доступа к Студии. Вы должны стать автором, чтобы получить доступ.')
        return redirect('become_author')
    
    try:
        categories = Category.objects.all()
        
        username = request.user.username
        bucket = get_bucket(BUCKET_NAME)
        
        if bucket:
            # Just check if metadata folder has any files
            metadata_prefix = f"{username}/metadata/"
            metadata_blobs = list(bucket.list_blobs(prefix=metadata_prefix, max_results=1))
            has_videos = len(metadata_blobs) > 0
        else:
            has_videos = False
        
        # Return the template with either placeholders or empty state
        return render(request, 'studio/studio.html', {
            'categories': categories,
            'has_videos': has_videos  # Flag to indicate if videos exist
        })
        
    except Exception as e:
        messages.error(request, f'Ошибка при получении данных: {e}')
        logger.error(f"Error in studio_view: {e}")
        
    return render(request, 'studio/studio.html', {
        'categories': categories if 'categories' in locals() else [],
        'has_videos': False
    })
    
@login_required
@require_http_methods(["DELETE"])
def delete_video_from_gcs(request, video_id):
    """
    Удаляет видео из S3
    """
    try:
        username = request.user.username
            
        from .s3_storage import delete_video
        success = delete_video(username, video_id)
        
        if success:
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'error': 'Не удалось удалить видео'}, status=400)
            
    except Exception as e:
        logger.error(f"Error deleting video: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def get_video_url(request, video_id):
    """
    Gets temporary URL for video or its thumbnail with quality selection.
    """
    try:
        # Check if specific user_id is provided in query parameters
        user_id = request.GET.get('user_id')
        
        # If no user_id provided in query params, check if video_id contains user info
        if not user_id and '__' in video_id:
            user_id, video_id = video_id.split('__', 1)
        
        # If still no user_id, default to current user
        if not user_id:
            user_id = request.user.username
            
        is_thumbnail = request.GET.get('thumbnail', 'false').lower() == 'true'
        quality = request.GET.get('quality')  # New parameter for quality selection
        
        # Get video metadata
        from .s3_storage import get_video_metadata, generate_video_url, get_video_url_with_quality
        metadata = get_video_metadata(user_id, video_id)
        
        if not metadata:
            return JsonResponse({'error': 'Video metadata not found'}, status=404)
        
        if is_thumbnail:
            thumbnail_path = metadata.get('thumbnail_path')
            if not thumbnail_path:
                return JsonResponse({'error': 'Video has no thumbnail'}, status=404)
                
            url = generate_video_url(user_id, video_id, file_path=thumbnail_path, expiration_time=3600)
            if url:
                return JsonResponse({
                    'success': True,
                    'url': url,
                    'is_thumbnail': True
                })
        else:
            # Generate URL for video with quality selection
            video_url_info = get_video_url_with_quality(user_id, video_id, quality, expiration_time=3600)
            
            if video_url_info and video_url_info['url']:
                return JsonResponse({
                    'success': True,
                    'url': video_url_info['url'],
                    'quality': video_url_info['quality'],
                    'available_qualities': video_url_info['available_qualities'],
                    'is_thumbnail': False
                })
        
        return JsonResponse({'error': 'Failed to generate URL'}, status=400)
            
    except Exception as e:
        logger.error(f"Error generating URL: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def get_thumbnail_url(request, video_id):
    """
    Отдельный эндпоинт для получения URL миниатюры для видео.
    """
    try:
        # Проверяем, содержит ли video_id составной идентификатор
        if '__' in video_id:
            user_id, gcs_video_id = video_id.split('__', 1)
        else:
            # Если пользователь авторизован, используем его ID
            if request.user.is_authenticated:
                user_id = request.user.username
                gcs_video_id = video_id
            else:
                return JsonResponse({'error': 'Необходимо указать ID пользователя в формате user__video'}, status=400)
        
        # Получаем метаданные видео
        from .s3_storage import get_video_metadata, generate_video_url
        
        metadata = get_video_metadata(user_id, gcs_video_id)
        if not metadata:
            return JsonResponse({'error': 'Метаданные видео не найдены'}, status=404)
        
        # Генерируем URL для миниатюры
        thumbnail_path = metadata.get('thumbnail_path')
        if not thumbnail_path:
            return JsonResponse({'error': 'У видео нет миниатюры'}, status=404)
            
        url = generate_video_url(user_id, gcs_video_id, file_path=thumbnail_path, expiration_time=3600)
        
        if url:
            return JsonResponse({
                'success': True,
                'url': url
            })
        else:
            return JsonResponse({'error': 'Не удалось сгенерировать URL миниатюры'}, status=400)
            
    except Exception as e:
        logger.error(f"Error generating thumbnail URL: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["GET"])
def refresh_metadata_cache(request):
    """
    API для принудительного обновления кэша метаданных видео.
    Требует аутентификации и доступен только админам.
    """
    try:
        # Проверяем, является ли пользователь суперпользователем
        if not request.user.is_superuser:
            return JsonResponse({
                'success': False,
                'error': 'Доступ запрещен. Требуются права администратора.'
            }, status=403)
            
        # Обновляем кэш метаданных
        success = cache_video_metadata()
        
        if success:
            return JsonResponse({
                'success': True,
                'message': 'Кэш метаданных видео успешно обновлен'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Не удалось обновить кэш метаданных'
            }, status=500)
            
    except Exception as e:
        logger.error(f"Error refreshing metadata cache: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
        
@login_required
@require_http_methods(["POST"])
def add_comment(request):
    """
    API endpoint to add a new comment (question) to a video with improved debugging and search
    """
    try:
        # Get data from request
        text = request.POST.get('text')
        video_id = request.POST.get('video_id')
        
        if not text or not video_id:
            return JsonResponse({'success': False, 'error': 'Не указан текст комментария или ID видео'}, status=400)
        
        # Get user info
        user = request.user
        username = user.username
        
        # Enhanced logging for debugging
        logger.info(f"Adding comment to video ID: {video_id}")
        logger.info(f"By user: {username}")
        
        # First check if the video ID contains user information
        video_owner_id = None
        actual_video_id = video_id
        
        if '__' in video_id:
            # Format might be user_id__video_id
            parts = video_id.split('__', 1)
            if len(parts) == 2:
                video_owner_id = parts[0]
                actual_video_id = parts[1]
                logger.info(f"Composite ID detected: owner={video_owner_id}, video_id={actual_video_id}")
        
        # If we don't have the owner ID yet, try to find it
        if not video_owner_id:
            logger.info(f"Checking if current user is the owner...")
            video_metadata = get_video_metadata(username, actual_video_id)
            
            if video_metadata:
                video_owner_id = username
                logger.info(f"Current user is the owner of the video")
            else:
                # If not found, try to find the owner among all users
                logger.info(f"Current user is not the owner, searching among all users...")
                
                bucket = get_bucket(BUCKET_NAME)
                if not bucket:
                    return JsonResponse({'success': False, 'error': 'Не удалось подключиться к хранилищу'}, status=500)
                
                # Get list of users from GCS
                blobs = bucket.list_blobs(delimiter='/')
                prefixes = list(blobs.prefixes)
                users = [prefix.replace('/', '') for prefix in prefixes 
                        if not prefix.startswith('system/')]
                
                logger.info(f"Found {len(users)} users to check")
                
                # Look for the video among all users
                found = False
                for user_id in users:
                    # Skip if it's the current user (already checked)
                    if user_id == username:
                        continue
                        
                    logger.info(f"Checking user: {user_id}")
                    metadata = get_video_metadata(user_id, actual_video_id)
                    if metadata:
                        video_owner_id = user_id
                        found = True
                        logger.info(f"Found video owner: {user_id}")
                        break
                
                # If still not found, try one more approach - using the exact video ID
                if not found and video_owner_id is None:  # Only set this if we haven't found a video owner yet
                    # Try to extract from the URL if possible
                    if '__' in video_id:
                        video_owner_id = video_id.split('__', 1)[0]
                        logger.info(f"Using video owner from URL: {video_owner_id}")
                    else:
                        logger.error(f"Could not determine video owner for ID: {actual_video_id}")
                        return JsonResponse({'success': False, 'error': 'Видео не найдено - не удалось определить владельца'}, status=404)
        
        # Если мы все еще не имеем owner ID после всех попыток, возвращаем ошибку
        if not video_owner_id:
            logger.error(f"Could not determine video owner for ID: {actual_video_id}")
            return JsonResponse({'success': False, 'error': 'Видео не найдено - не удалось определить владельца'}, status=404)
            
        logger.info(f"Final video owner: {video_owner_id}")
        from .s3_storage import add_comment as s3_add_comment, get_user_profile_from_gcs
        # Получаем отображаемое имя из профиля пользователя
        display_name = user.profile.display_name if hasattr(user, 'profile') and user.profile.display_name else username
        
        # Получаем профиль пользователя для URL аватара
        user_profile = get_user_profile_from_gcs(username)
        avatar_url = user_profile.get('avatar_url', None) if user_profile else None
        
        # Используйте переименованную функцию
        success = s3_add_comment(
            user_id=video_owner_id,  # Use the determined video owner ID
            video_id=actual_video_id,  # Use the actual video ID (without user prefix)
            comment_user_id=username,
            comment_text=text,
            display_name=display_name,
            avatar_url=avatar_url
        )
        
        if not success:
            logger.error(f"Failed to add comment to video {actual_video_id} for owner {video_owner_id}")
            return JsonResponse({'success': False, 'error': 'Не удалось добавить комментарий'}, status=500)
        
        # Return success response with comment data
        import uuid
        from datetime import datetime
        
        # В ответе также включаем URL аватара
        comment_data = {
            'id': str(uuid.uuid4()),  # Generate random ID for now (GCS should return real ID)
            'user_id': username,
            'display_name': display_name,
            'text': text,
            'date': datetime.now().isoformat(),
            'likes': 0,
            'replies': [],
            'avatar_url': avatar_url  # Добавляем URL аватара в ответ
        }
        
        logger.info(f"Comment successfully added")
        return JsonResponse({'success': True, 'comment': comment_data})
        
    except Exception as e:
        logger.error(f"Error adding comment: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def add_reply(request):
    """
    API endpoint to add a reply to a comment with improved debugging and search
    """
    try:
        # Get data from request
        text = request.POST.get('text')
        comment_id = request.POST.get('comment_id')
        video_id = request.POST.get('video_id')
        
        if not text or not comment_id or not video_id:
            return JsonResponse({'success': False, 'error': 'Не указаны необходимые данные'}, status=400)
        
        # Get user info
        user = request.user
        username = user.username
        
        # Enhanced logging for debugging
        logger.info(f"Adding reply to comment ID: {comment_id}")
        logger.info(f"On video ID: {video_id}")
        logger.info(f"By user: {username}")
        
        # First check if the video ID contains user information
        video_owner_id = None
        actual_video_id = video_id
        
        if '__' in video_id:
            # Format might be user_id__video_id
            parts = video_id.split('__', 1)
            if len(parts) == 2:
                video_owner_id = parts[0]
                actual_video_id = parts[1]
                logger.info(f"Composite ID detected: owner={video_owner_id}, video_id={actual_video_id}")
        
        # If we don't have the owner ID yet, try to find it
        if not video_owner_id:
            # Try first with current user
            logger.info(f"Checking if current user is the owner...")
            video_metadata = get_video_metadata(username, actual_video_id)
            
            if video_metadata:
                video_owner_id = username
                logger.info(f"Current user is the owner of the video")
            else:
                # If not found, try to find the owner among all users
                logger.info(f"Current user is not the owner, searching among all users...")
                
                bucket = get_bucket(BUCKET_NAME)
                if not bucket:
                    return JsonResponse({'success': False, 'error': 'Не удалось подключиться к хранилищу'}, status=500)
                
                # Get list of users from GCS
                blobs = bucket.list_blobs(delimiter='/')
                prefixes = list(blobs.prefixes)
                users = [prefix.replace('/', '') for prefix in prefixes 
                        if not prefix.startswith('system/')]
                
                logger.info(f"Found {len(users)} users to check")
                
                # Look for the video among all users
                found = False
                for user_id in users:
                    # Skip if it's the current user (already checked)
                    if user_id == username:
                        continue
                        
                    logger.info(f"Checking user: {user_id}")
                    metadata = get_video_metadata(user_id, actual_video_id)
                    if metadata:
                        video_owner_id = user_id
                        found = True
                        logger.info(f"Found video owner: {user_id}")
                        break
                
                # Если владелец видео всё ещё не найден, используем значение из URL
                if not found and '__' in video_id:
                    video_owner_id = video_id.split('__', 1)[0]
                    logger.warning(f"Video not found by direct ID match, using URL-provided owner ID: {video_owner_id}")
                # Если в URL не был указан владелец и мы не нашли видео, возвращаем ошибку
                elif not found:
                    logger.error(f"Could not determine video owner for ID: {actual_video_id}")
                    return JsonResponse({'success': False, 'error': 'Видео не найдено - не удалось определить владельца'}, status=404)
        
        # If we still don't have an owner ID, we can't proceed
        if not video_owner_id:
            logger.error(f"Could not determine video owner for ID: {actual_video_id}")
            return JsonResponse({'success': False, 'error': 'Видео не найдено - не удалось определить владельца'}, status=404)
            
        logger.info(f"Final video owner: {video_owner_id}")
        from .s3_storage import add_reply as s3_add_reply, get_user_profile_from_gcs
        # Получаем отображаемое имя из профиля пользователя
        display_name = user.profile.display_name if hasattr(user, 'profile') and user.profile.display_name else username
        
        user_profile = get_user_profile_from_gcs(username)
        avatar_url = user_profile.get('avatar_url', None) if user_profile else None
        
        # Add reply
        success = s3_add_reply(
            user_id=video_owner_id,
            video_id=actual_video_id,
            comment_id=comment_id,
            reply_user_id=username,
            reply_text=text,
            display_name=display_name,
            avatar_url=avatar_url
        )
        
        if not success:
            logger.error(f"Failed to add reply to comment {comment_id} on video {actual_video_id}")
            return JsonResponse({'success': False, 'error': 'Не удалось добавить ответ'}, status=500)
        
        # Return success response with reply data
        import uuid
        from datetime import datetime
        reply_data = {
            'id': str(uuid.uuid4()),  # Generate random ID for now
            'user_id': username,
            'display_name': display_name,
            'text': text,
            'date': datetime.now().isoformat(),
            'likes': 0,
            'avatar_url': avatar_url  # Добавляем URL аватара
        }
        
        logger.info(f"Reply successfully added")
        return JsonResponse({'success': True, 'reply': reply_data})
        
    except Exception as e:
        logger.error(f"Error adding reply: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def track_video_view(request):
    """
    API endpoint for tracking video views
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    try:
        video_id = request.POST.get('video_id')
        user_id = request.POST.get('user_id')
        session_id = request.POST.get('session_id')

        if not video_id or not user_id:
            return JsonResponse({'success': False, 'error': 'Missing video_id or user_id'}, status=400)

        # Разделяем составной ID
        if '__' in video_id:
            user_id, video_id = video_id.split('__', 1)

        # Получаем метаданные видео
        metadata = get_video_metadata(user_id, video_id)
        if not metadata:
            return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)

        # Проверяем, был ли уже просмотр
        view_exists = False
        with transaction.atomic():
            if request.user.is_authenticated:
                # Для авторизованных пользователей
                view_exists = VideoView.objects.filter(
                    user=request.user,
                    video_id=video_id,
                    video_owner=user_id
                ).exists()
            else:
                # Для неавторизованных пользователей используем session_id
                if not session_id:
                    return JsonResponse({'success': False, 'error': 'Session ID required for non-authenticated users'}, status=400)
                view_exists = VideoView.objects.filter(
                    session_id=session_id,
                    video_id=video_id,
                    video_owner=user_id
                ).exists()

            if not view_exists:
                # Регистрируем новый просмотр
                metadata['views'] = int(metadata.get('views', 0)) + 1
                VideoView.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    video_id=video_id,
                    video_owner=user_id,
                    session_id=session_id if not request.user.is_authenticated else None
                )

                # Обновляем метаданные в GCS
                if not update_video_metadata(user_id, video_id, metadata):
                    return JsonResponse({'success': False, 'error': 'Failed to update metadata'}, status=500)

        return JsonResponse({
            'success': True,
            'views': metadata.get('views', 0),
            'view_counted': not view_exists
        })

    except Exception as e:
        logger.error(f"Error tracking view: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def get_client_ip(request):
    """Получает IP-адрес клиента из заголовков запроса"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip