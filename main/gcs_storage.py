from google.cloud import storage
import os
import json
from datetime import datetime
from django.conf import settings
import logging
import mimetypes
import uuid

# Set up logging
logger = logging.getLogger(__name__)

BUCKET_NAME = "kronik-portage"

def find_json_file(start_dir=None, filename_part="kronik-26102005-0ec8103ffcf3.json"):
    import os
    from django.conf import settings
    search_dirs = [
        os.getcwd(), 
        settings.BASE_DIR,
        os.path.join(settings.BASE_DIR, 'config'),
        os.path.join(settings.BASE_DIR, 'credentials'),
        os.path.join(settings.BASE_DIR, 'keys'),
    ]
    
    if start_dir:
        search_dirs.insert(0, start_dir)
    
    for root_dir in search_dirs:
        for root, dirs, files in os.walk(root_dir):
            matching_files = [
                os.path.join(root, file) 
                for file in files 
                if filename_part in file and file.endswith('.json')
            ]
            
            if matching_files:
                logger.info(f"Found JSON file: {matching_files[0]}")
                return matching_files[0]
    
    logger.error("JSON file for Google Cloud not found!")
    return None

def init_gcs_client():
    try:
        credentials_path = find_json_file()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        from google.cloud import storage
        client = storage.Client()
        return client
    
    except Exception as e:
        logger.error(f"Error initializing GCS client: {e}")
        return None

def connect_to_gcs():
    """ Подключается к Google Cloud Storage и выводит список бакетов """
    try:
        client = storage.Client()
        buckets = list(client.list_buckets())
        
        if not buckets:
            logger.info("No available buckets")
        else:
            logger.info("Available buckets:")
            for bucket in buckets:
                logger.info(f"- {bucket.name}")
        
        return client
    except Exception as e:
        logger.error(f"Error connecting to GCS: {e}")
        return None

def get_bucket(bucket_name=BUCKET_NAME):
    """Получает бакет по имени, создает если не существует"""
    try:
        client = init_gcs_client()
        if not client:
            raise Exception("Failed to initialize GCS client")
            
        bucket = client.bucket(bucket_name)
        
        if not bucket.exists():
            logger.info(f"Bucket {bucket_name} does not exist, creating it...")
        
        return bucket
    except Exception as e:
        logger.error(f"Error getting bucket: {e}")
        return None

def create_user_folder_structure(user_id):
    """
    Создает структуру папок для пользователя.
    
    Args:
        user_id (str): Имя пользователя (с префиксом @)
        
    Returns:
        bool: True если успешно, False в противном случае
    """
    try:
        bucket = get_bucket()
        if not bucket:
            logger.error(f"Could not get bucket for user {user_id}")
            return False
        
        # Определяем типы папок для создания
        folder_types = ["videos", "previews", "metadata", "comments", "bio"]
        
        for folder_type in folder_types:
            folder_path = f"{user_id}/{folder_type}/"
            
            # Создаем пустой маркерный файл, так как GCS не имеет реальных папок
            marker_blob = bucket.blob(f"{folder_path}.keep")
            marker_blob.upload_from_string('')
            logger.info(f"Created folder {folder_path}")
        
        # Создаем начальные пустые файлы comments.json и метаданные пользователя
        init_user_files(user_id, bucket)
        
        logger.info(f"Successfully created folder structure for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating folder structure for user {user_id}: {str(e)}")
        return False

def init_user_files(user_id, bucket):
    """Инициализация важных файлов пользователя"""
    try:
        # Создаем пустые метаданные пользователя
        user_meta = {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "display_name": "",
            "avatar_path": "",
            "stats": {
                "videos_count": 0,
                "total_views": 0
            }
        }
        
        # Сохраняем метаданные пользователя
        meta_blob = bucket.blob(f"{user_id}/bio/user_meta.json")
        meta_blob.upload_from_string(json.dumps(user_meta, indent=2), content_type='application/json')
        
        # Создаем приветственный файл
        welcome_blob = bucket.blob(f"{user_id}/bio/welcome.txt")
        welcome_message = f"Welcome to KRONIK, {user_id}! This is your personal storage space."
        welcome_blob.upload_from_string(welcome_message, content_type='text/plain')
        
        return True
    except Exception as e:
        logger.error(f"Error initializing user files for {user_id}: {e}")
        return False

def upload_video(user_id, video_file_path, title=None, description=None):
    """
    Загружает видеофайл в хранилище и создает соответствующие метаданные
    
    Parameters:
    - user_id: ID пользователя или имя пользователя (с префиксом @)
    - video_file_path: Путь к видеофайлу на локальном компьютере
    - title: Название видео (опционально)
    - description: Описание видео (опционально)
    
    Returns:
    - video_id: ID видео в формате даты и имени файла
    """
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for video upload")
        return None
    
    # Создаем структуру папок, если она еще не существует
    create_user_folder_structure(user_id)
    
    # Генерируем ID видео на основе даты и имени файла
    now = datetime.now()
    date_prefix = now.strftime("%Y-%m-%d")
    
    # Получаем имя файла из пути
    file_name = os.path.basename(video_file_path)
    base_name = os.path.splitext(file_name)[0]
    file_extension = os.path.splitext(file_name)[1]
    
    # Формируем ID видео
    video_id = f"{date_prefix}_{base_name}"
    
    # Формируем пути для хранения
    video_path = f"{user_id}/videos/{video_id}{file_extension}"
    metadata_path = f"{user_id}/metadata/{video_id}.json"
    comments_path = f"{user_id}/comments/{video_id}_comments.json"
    
    try:
        # Получаем размер файла и MIME-тип
        file_size = os.path.getsize(video_file_path)
        mime_type = mimetypes.guess_type(video_file_path)[0] or 'video/mp4'
        
        # Загружаем видео
        video_blob = bucket.blob(video_path)
        video_blob.upload_from_filename(video_file_path, content_type=mime_type)
        
        # Создаем метаданные
        metadata = {
            "video_id": video_id,
            "user_id": user_id,
            "title": title or base_name,
            "description": description or "",
            "upload_date": now.isoformat(),
            "file_path": video_path,
            "file_size": file_size,
            "mime_type": mime_type,
            "views": 0,
            "likes": 0,
            "dislikes": 0,
            "duration": "00:00",  # Это будет обновлено с реальной продолжительностью, если доступно
            "status": "published"
        }
        
        # Сохраняем метаданные
        metadata_blob = bucket.blob(metadata_path)
        metadata_blob.upload_from_string(json.dumps(metadata, indent=2), content_type='application/json')
        
        # Создаем пустой файл комментариев
        comments = {
            "video_id": video_id,
            "comments": []
        }
        comments_blob = bucket.blob(comments_path)
        comments_blob.upload_from_string(json.dumps(comments, indent=2), content_type='application/json')
        
        # Обновляем статистику пользователя
        update_user_stats(user_id, bucket)
        
        logger.info(f"Video {video_id} successfully uploaded")
        return video_id
    
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        return None

def update_user_stats(user_id, bucket=None):
    """Обновляет статистику пользователя в метаданных"""
    if not bucket:
        bucket = get_bucket()
        if not bucket:
            return False
    
    try:
        # Получаем метаданные пользователя
        user_meta_path = f"{user_id}/bio/user_meta.json"
        user_meta_blob = bucket.blob(user_meta_path)
        
        if user_meta_blob.exists():
            user_meta = json.loads(user_meta_blob.download_as_text())
        else:
            user_meta = {
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "stats": {}
            }
        
        # Считаем видео
        videos_list = list_user_videos(user_id, bucket)
        videos_count = len(videos_list)
        
        # Вычисляем общее количество просмотров
        total_views = sum(video.get('views', 0) for video in videos_list)
        
        # Обновляем статистику
        if "stats" not in user_meta:
            user_meta["stats"] = {}
            
        user_meta["stats"]["videos_count"] = videos_count
        user_meta["stats"]["total_views"] = total_views
        user_meta["last_updated"] = datetime.now().isoformat()
        
        # Сохраняем обновленные метаданные
        user_meta_blob.upload_from_string(json.dumps(user_meta, indent=2), content_type='application/json')
        return True
        
    except Exception as e:
        logger.error(f"Error updating user stats: {e}")
        return False

def upload_thumbnail(user_id, video_id, thumbnail_file_path):
    """Загружает миниатюру для видео"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for thumbnail upload")
        return False
    
    file_extension = os.path.splitext(thumbnail_file_path)[1]
    thumbnail_path = f"{user_id}/previews/{video_id}{file_extension}"
    
    try:
        # Определяем MIME-тип
        mime_type = mimetypes.guess_type(thumbnail_file_path)[0] or 'image/jpeg'
        
        thumbnail_blob = bucket.blob(thumbnail_path)
        thumbnail_blob.upload_from_filename(thumbnail_file_path, content_type=mime_type)
        
        # Обновляем метаданные с информацией о миниатюре
        metadata_path = f"{user_id}/metadata/{video_id}.json"
        metadata_blob = bucket.blob(metadata_path)
        
        if metadata_blob.exists():
            metadata_content = json.loads(metadata_blob.download_as_text())
            metadata_content["thumbnail_path"] = thumbnail_path
            metadata_content["thumbnail_mime_type"] = mime_type
            metadata_blob.upload_from_string(json.dumps(metadata_content, indent=2), content_type='application/json')
        
        logger.info(f"Thumbnail for video {video_id} successfully uploaded")
        return True
    
    except Exception as e:
        logger.error(f"Error uploading thumbnail: {e}")
        return False

def add_comment(user_id, video_id, comment_user_id, comment_text, display_name=None):
    """Добавляет комментарий к видео"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for adding comment")
        return False
        
    comments_path = f"{user_id}/comments/{video_id}_comments.json"
    
    try:
        comments_blob = bucket.blob(comments_path)
        
        if comments_blob.exists():
            comments_data = json.loads(comments_blob.download_as_text())
        else:
            comments_data = {"comments": []}
        
        # Генерируем уникальный ID комментария
        comment_id = str(uuid.uuid4())
        
        # Добавляем новый комментарий
        new_comment = {
            "id": comment_id,
            "user_id": comment_user_id,
            "display_name": display_name or comment_user_id,
            "text": comment_text,
            "date": datetime.now().isoformat(),
            "likes": 0,
            "replies": []
        }
        
        comments_data["comments"].append(new_comment)
        
        # Сохраняем обновленные комментарии
        comments_blob.upload_from_string(json.dumps(comments_data, indent=2), content_type='application/json')
        
        logger.info(f"Comment added to video {video_id}")
        return True
    
    except Exception as e:
        logger.error(f"Error adding comment: {e}")
        return False

def add_reply(user_id, video_id, comment_id, reply_user_id, reply_text, display_name=None):
    """Добавляет ответ на комментарий"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for adding reply")
        return False
        
    comments_path = f"{user_id}/comments/{video_id}_comments.json"
    
    try:
        comments_blob = bucket.blob(comments_path)
        
        if not comments_blob.exists():
            logger.error(f"Comments file not found for video {video_id}")
            return False
            
        comments_data = json.loads(comments_blob.download_as_text())
        
        # Находим комментарий, на который нужно ответить
        found = False
        for comment in comments_data.get("comments", []):
            if comment.get("id") == comment_id:
                # Генерируем уникальный ID ответа
                reply_id = str(uuid.uuid4())
                
                # Создаем объект ответа
                reply = {
                    "id": reply_id,
                    "user_id": reply_user_id,
                    "display_name": display_name or reply_user_id,
                    "text": reply_text,
                    "date": datetime.now().isoformat(),
                    "likes": 0
                }
                
                # Добавляем ответ к комментарию
                if "replies" not in comment:
                    comment["replies"] = []
                    
                comment["replies"].append(reply)
                found = True
                break
        
        if not found:
            logger.error(f"Comment {comment_id} not found in video {video_id}")
            return False
            
        # Сохраняем обновленные комментарии
        comments_blob.upload_from_string(json.dumps(comments_data, indent=2), content_type='application/json')
        
        logger.info(f"Reply added to comment {comment_id} in video {video_id}")
        return True
    
    except Exception as e:
        logger.error(f"Error adding reply: {e}")
        return False

def get_video_metadata(user_id, video_id):
    """Получает метаданные видео"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for retrieving metadata")
        return None
        
    metadata_path = f"{user_id}/metadata/{video_id}.json"
    
    try:
        metadata_blob = bucket.blob(metadata_path)
        
        if metadata_blob.exists():
            return json.loads(metadata_blob.download_as_text())
        else:
            logger.warning(f"Metadata for video {video_id} not found")
            return None
    
    except Exception as e:
        logger.error(f"Error retrieving metadata: {e}")
        return None

def get_video_comments(user_id, video_id):
    """Получает комментарии к видео"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for retrieving comments")
        return {"comments": []}
        
    comments_path = f"{user_id}/comments/{video_id}_comments.json"
    
    try:
        comments_blob = bucket.blob(comments_path)
        
        if comments_blob.exists():
            return json.loads(comments_blob.download_as_text())
        else:
            logger.warning(f"Comments for video {video_id} not found")
            return {"comments": []}
    
    except Exception as e:
        logger.error(f"Error retrieving comments: {e}")
        return {"comments": []}

def list_user_videos(user_id, bucket=None):
    """Возвращает список всех видео пользователя"""
    if not bucket:
        bucket = get_bucket()
        if not bucket:
            logger.error(f"Could not get bucket for listing videos")
            return []
        
    metadata_prefix = f"{user_id}/metadata/"
    
    videos_list = []
    
    try:
        blobs = bucket.list_blobs(prefix=metadata_prefix)
        
        for blob in blobs:
            if blob.name.endswith('.json'):
                metadata = json.loads(blob.download_as_text())
                videos_list.append(metadata)
        
        # Сортируем по дате загрузки (сначала новые)
        videos_list.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
        
        return videos_list
    
    except Exception as e:
        logger.error(f"Error getting video list: {e}")
        return []

def delete_video(user_id, video_id):
    """Удаляет видео и все связанные файлы"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for deleting video")
        return False
    
    # Получаем метаданные для определения путей файлов
    metadata = get_video_metadata(user_id, video_id)
    
    if not metadata:
        logger.error(f"Metadata for video {video_id} not found, cannot delete")
        return False
    
    try:
        # Удаляем файл видео
        if "file_path" in metadata:
            video_blob = bucket.blob(metadata["file_path"])
            if video_blob.exists():
                video_blob.delete()
                logger.info(f"Video file {video_id} deleted")
        
        # Удаляем миниатюру
        if "thumbnail_path" in metadata:
            thumbnail_blob = bucket.blob(metadata["thumbnail_path"])
            if thumbnail_blob.exists():
                thumbnail_blob.delete()
                logger.info(f"Thumbnail for video {video_id} deleted")
        
        # Удаляем метаданные
        metadata_path = f"{user_id}/metadata/{video_id}.json"
        metadata_blob = bucket.blob(metadata_path)
        if metadata_blob.exists():
            metadata_blob.delete()
            logger.info(f"Metadata for video {video_id} deleted")
        
        # Удаляем комментарии
        comments_path = f"{user_id}/comments/{video_id}_comments.json"
        comments_blob = bucket.blob(comments_path)
        if comments_blob.exists():
            comments_blob.delete()
            logger.info(f"Comments for video {video_id} deleted")
        
        # Обновляем статистику пользователя после удаления
        update_user_stats(user_id, bucket)
        
        logger.info(f"Video {video_id} and all related files successfully deleted")
        return True
    
    except Exception as e:
        logger.error(f"Error deleting video: {e}")
        return False

def generate_video_url(user_id, video_id, file_path=None, expiration_time=3600):
    """Генерирует временную URL-ссылку для доступа к видео"""
    metadata = get_video_metadata(user_id, video_id)
    
    if not file_path and (not metadata or "file_path" not in metadata):
        logger.error(f"Could not find information about video {video_id}")
        return None
    
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for generating URL")
        return None
        
    # Используем предоставленный путь к файлу или берем из метаданных
    path_to_use = file_path if file_path else metadata["file_path"]
    video_blob = bucket.blob(path_to_use)
    
    if not video_blob.exists():
        logger.error(f"File not found in storage at path: {path_to_use}")
        return None
    
    try:
        url = video_blob.generate_signed_url(
            version="v4",
            expiration=expiration_time,
            method="GET"
        )
        
        logger.info(f"Generated temporary URL for file (valid for {expiration_time} seconds)")
        return url
    
    except Exception as e:
        logger.error(f"Error generating URL: {e}")
        return None

def update_user_profile_in_gcs(user_id, display_name=None, bio=None, profile_picture_path=None):
    """
    Обновляет информацию профиля пользователя в GCS
    
    Parameters:
    - user_id: ID пользователя или имя пользователя (с префиксом @)
    - display_name: Отображаемое имя пользователя
    - bio: Текст биографии пользователя
    - profile_picture_path: Путь к файлу изображения профиля (локальный)
    
    Returns:
    - True если успешно, False в противном случае
    """
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for updating user profile")
        return False
    
    try:
        # Получаем текущие метаданные пользователя
        user_meta_path = f"{user_id}/bio/user_meta.json"
        user_meta_blob = bucket.blob(user_meta_path)
        
        if user_meta_blob.exists():
            user_meta = json.loads(user_meta_blob.download_as_text())
        else:
            user_meta = {
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
            }
        
        # Обновляем отображаемое имя, если предоставлено
        if display_name:
            user_meta["display_name"] = display_name
        
        # Обновляем биографию, если предоставлена
        if bio:
            bio_blob = bucket.blob(f"{user_id}/bio/bio.txt")
            bio_blob.upload_from_string(bio, content_type='text/plain')
            user_meta["has_bio"] = True
        
        # Обработка изображения профиля
        is_default_image = False
        
        # Проверяем, нужно ли удалить аватар
        if profile_picture_path and 'default.png' in profile_picture_path.lower():
            is_default_image = True
            # Если есть существующий аватар, удаляем его
            if "avatar_path" in user_meta:
                try:
                    existing_avatar_blob = bucket.blob(user_meta["avatar_path"])
                    if existing_avatar_blob.exists():
                        existing_avatar_blob.delete()
                        logger.info(f"Deleted existing avatar for user {user_id}")
                except Exception as e:
                    logger.error(f"Error deleting existing avatar: {e}")
            
            # Устанавливаем метаданные для дефолтного аватара
            if os.path.exists(profile_picture_path):
                file_extension = os.path.splitext(profile_picture_path)[1].lower()
                avatar_path = f"{user_id}/bio/default_avatar{file_extension}"
                
                # Загружаем дефолтное изображение профиля
                avatar_blob = bucket.blob(avatar_path)
                mime_type = mimetypes.guess_type(profile_picture_path)[0] or 'image/png'
                avatar_blob.upload_from_filename(profile_picture_path, content_type=mime_type)
                
                # Обновляем метаданные с путем к аватару
                user_meta["avatar_path"] = avatar_path
                user_meta["is_default_avatar"] = True
        elif profile_picture_path and os.path.exists(profile_picture_path):
            # Если загружен новый аватар, удаляем старый (если есть)
            if "avatar_path" in user_meta:
                try:
                    existing_avatar_blob = bucket.blob(user_meta["avatar_path"])
                    if existing_avatar_blob.exists():
                        existing_avatar_blob.delete()
                        logger.info(f"Deleted existing avatar for user {user_id}")
                except Exception as e:
                    logger.error(f"Error deleting existing avatar: {e}")
            
            # Загружаем новый аватар
            file_extension = os.path.splitext(profile_picture_path)[1].lower()
            avatar_path = f"{user_id}/bio/avatar{file_extension}"
            
            avatar_blob = bucket.blob(avatar_path)
            mime_type = mimetypes.guess_type(profile_picture_path)[0] or 'image/jpeg'
            avatar_blob.upload_from_filename(profile_picture_path, content_type=mime_type)
            
            # Обновляем метаданные с путем к аватару
            user_meta["avatar_path"] = avatar_path
            user_meta["is_default_avatar"] = False
        
        # Обновляем временную метку
        user_meta["last_updated"] = datetime.now().isoformat()
        
        # Сохраняем обновленные метаданные
        user_meta_blob.upload_from_string(json.dumps(user_meta, indent=2), content_type='application/json')
        
        logger.info(f"User profile for {user_id} successfully updated in GCS")
        return True
        
    except Exception as e:
        logger.error(f"Error updating user profile in GCS: {e}")
        return False

def get_user_profile_from_gcs(user_id):
    """Получает информацию профиля пользователя из GCS"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for retrieving user profile")
        return None
    
    try:
        # Получаем метаданные пользователя
        user_meta_path = f"{user_id}/bio/user_meta.json"
        user_meta_blob = bucket.blob(user_meta_path)
        
        if not user_meta_blob.exists():
            logger.warning(f"User metadata not found for {user_id}")
            return None
        
        # Загружаем метаданные пользователя
        user_meta = json.loads(user_meta_blob.download_as_text())
        
        # Получаем биографию, если существует
        bio_blob = bucket.blob(f"{user_id}/bio/bio.txt")
        if bio_blob.exists():
            user_meta["bio"] = bio_blob.download_as_text()
        else:
            user_meta["bio"] = ""
        
        # Генерируем URL для аватара, если существует
        if "avatar_path" in user_meta and user_meta["avatar_path"]:
            avatar_blob = bucket.blob(user_meta["avatar_path"])
            if avatar_blob.exists():
                user_meta["avatar_url"] = avatar_blob.generate_signed_url(
                    version="v4",
                    expiration=3600*24,  # 24 часа
                    method="GET"
                )
        
        return user_meta
    
    except Exception as e:
        logger.error(f"Error retrieving user profile from GCS: {e}")
        return None