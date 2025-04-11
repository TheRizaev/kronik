from google.cloud import storage
import os
import json
from datetime import datetime
from django.conf import settings
import logging

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
    try:
        bucket = get_bucket()
        if not bucket:
            logger.error(f"Could not get bucket for user {user_id}")
            return False
        
        # Define folder types to create
        folder_types = ["videos", "previews", "metadata", "comments", "bio"]
        
        for folder_type in folder_types:
            folder_path = f"{user_id}/{folder_type}/"
            
            # Create empty marker file since GCS doesn't have real folders
            marker_blob = bucket.blob(f"{folder_path}.keep")
            marker_blob.upload_from_string('')
            logger.info(f"Created folder {folder_path}")
        
        logger.info(f"Successfully created folder structure for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating folder structure for user {user_id}: {str(e)}")
        return False

def upload_video(user_id, video_file_path, title=None, description=None):
    """
    Загружает видеофайл в хранилище и создает соответствующие метаданные
    
    Parameters:
    - user_id: ID пользователя или username
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
        # Загружаем видео
        video_blob = bucket.blob(video_path)
        video_blob.upload_from_filename(video_file_path)
        
        # Создаем метаданные
        metadata = {
            "video_id": video_id,
            "user_id": user_id,
            "title": title or base_name,
            "description": description or "",
            "upload_date": now.isoformat(),
            "file_path": video_path,
            "file_size": os.path.getsize(video_file_path),
            "views": 0
        }
        
        # Сохраняем метаданные
        metadata_blob = bucket.blob(metadata_path)
        metadata_blob.upload_from_string(json.dumps(metadata, indent=2), content_type='application/json')
        
        # Создаем пустой файл комментариев
        comments = {"comments": []}
        comments_blob = bucket.blob(comments_path)
        comments_blob.upload_from_string(json.dumps(comments, indent=2), content_type='application/json')
        
        logger.info(f"Video {video_id} successfully uploaded")
        return video_id
    
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        return None

def upload_thumbnail(user_id, video_id, thumbnail_file_path):
    """Загружает миниатюру для видео"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for thumbnail upload")
        return False
    
    file_extension = os.path.splitext(thumbnail_file_path)[1]
    thumbnail_path = f"{user_id}/previews/{video_id}{file_extension}"
    
    try:
        thumbnail_blob = bucket.blob(thumbnail_path)
        thumbnail_blob.upload_from_filename(thumbnail_file_path)
        
        # Обновляем метаданные с информацией о миниатюре
        metadata_path = f"{user_id}/metadata/{video_id}.json"
        metadata_blob = bucket.blob(metadata_path)
        
        if metadata_blob.exists():
            metadata_content = json.loads(metadata_blob.download_as_text())
            metadata_content["thumbnail_path"] = thumbnail_path
            metadata_blob.upload_from_string(json.dumps(metadata_content, indent=2), content_type='application/json')
        
        logger.info(f"Thumbnail for video {video_id} successfully uploaded")
        return True
    
    except Exception as e:
        logger.error(f"Error uploading thumbnail: {e}")
        return False

def add_comment(user_id, video_id, comment_user_id, comment_text):
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
        
        # Добавляем новый комментарий
        new_comment = {
            "id": len(comments_data["comments"]) + 1,
            "user_id": comment_user_id,
            "text": comment_text,
            "date": datetime.now().isoformat()
        }
        
        comments_data["comments"].append(new_comment)
        
        # Сохраняем обновленные комментарии
        comments_blob.upload_from_string(json.dumps(comments_data, indent=2), content_type='application/json')
        
        logger.info(f"Comment added to video {video_id}")
        return True
    
    except Exception as e:
        logger.error(f"Error adding comment: {e}")
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

def download_video(user_id, video_id, destination_folder="."):
    """Скачивает видео на локальный компьютер"""
    metadata = get_video_metadata(user_id, video_id)
    
    if not metadata or "file_path" not in metadata:
        logger.error(f"Could not find information about video {video_id}")
        return False
    
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for downloading video")
        return False
        
    video_blob = bucket.blob(metadata["file_path"])
    
    if not video_blob.exists():
        logger.error(f"Video file not found in storage")
        return False
    
    file_extension = os.path.splitext(metadata["file_path"])[1]
    destination_path = os.path.join(destination_folder, f"{video_id}{file_extension}")
    
    try:
        video_blob.download_to_filename(destination_path)
        logger.info(f"Video {video_id} downloaded to {destination_path}")
        return destination_path
    
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return False

def increment_view_count(user_id, video_id):
    """Увеличивает счетчик просмотров видео"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for incrementing view count")
        return None
        
    metadata_path = f"{user_id}/metadata/{video_id}.json"
    
    try:
        metadata_blob = bucket.blob(metadata_path)
        
        if metadata_blob.exists():
            metadata = json.loads(metadata_blob.download_as_text())
            metadata["views"] = metadata.get("views", 0) + 1
            metadata_blob.upload_from_string(json.dumps(metadata, indent=2), content_type='application/json')
            logger.info(f"View count for video {video_id} increased to {metadata['views']}")
            return metadata["views"]
        else:
            logger.warning(f"Metadata for video {video_id} not found")
            return None
    
    except Exception as e:
        logger.error(f"Error updating view count: {e}")
        return None

def list_user_videos(user_id):
    """Возвращает список всех видео пользователя"""
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
        
        logger.info(f"Video {video_id} and all related files successfully deleted")
        return True
    
    except Exception as e:
        logger.error(f"Error deleting video: {e}")
        return False

def get_user_storage_usage(user_id):
    """Возвращает информацию об использовании хранилища пользователем"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for retrieving storage usage")
        return None
        
    user_prefix = f"{user_id}/"
    
    total_size = 0
    file_counts = {
        "videos": 0,
        "previews": 0,
        "metadata": 0,
        "comments": 0,
        "bio": 0
    }
    
    try:
        blobs = bucket.list_blobs(prefix=user_prefix)
        
        for blob in blobs:
            if blob.size > 0:  # Игнорируем маркеры папок
                total_size += blob.size
                
                # Определяем тип файла по пути
                for file_type in file_counts.keys():
                    if f"/{file_type}/" in blob.name:
                        file_counts[file_type] += 1
                        break
        
        usage_info = {
            "user_id": user_id,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "file_counts": file_counts
        }
        
        return usage_info
    
    except Exception as e:
        logger.error(f"Error getting storage usage information: {e}")
        return None

def generate_video_url(user_id, video_id, expiration_time=3600):
    """Генерирует временную URL-ссылку для доступа к видео"""
    metadata = get_video_metadata(user_id, video_id)
    
    if not metadata or "file_path" not in metadata:
        logger.error(f"Could not find information about video {video_id}")
        return None
    
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for generating URL")
        return None
        
    video_blob = bucket.blob(metadata["file_path"])
    
    if not video_blob.exists():
        logger.error(f"Video file not found in storage")
        return None
    
    try:
        url = video_blob.generate_signed_url(
            version="v4",
            expiration=expiration_time,
            method="GET"
        )
        
        logger.info(f"Generated temporary URL for video {video_id} (valid for {expiration_time} seconds)")
        return url
    
    except Exception as e:
        logger.error(f"Error generating URL: {e}")
        return None

def search_videos(query, user_id=None):
    """
    Поиск видео по запросу в заголовке или описании
    
    Parameters:
    - query: Поисковый запрос
    - user_id: ID пользователя (если None, поиск по всем пользователям)
    
    Returns:
    - Список найденных видео
    """
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for searching videos")
        return []
    
    if user_id:
        prefix = f"{user_id}/metadata/"
    else:
        prefix = "*/metadata/"
    
    results = []
    query = query.lower()
    
    try:
        # Для общего поиска нужно сканировать все файлы метаданных
        if "*" in prefix:
            # Ищем папки пользователей
            user_folders = set()
            blobs = bucket.list_blobs(delimiter='/')
            for prefix_item in blobs.prefixes:
                user_folders.add(prefix_item.rstrip('/'))
            
            # Сканируем метаданные каждого пользователя
            for user_folder in user_folders:
                metadata_prefix = f"{user_folder}/metadata/"
                metadata_blobs = bucket.list_blobs(prefix=metadata_prefix)
                
                for blob in metadata_blobs:
                    if blob.name.endswith('.json'):
                        metadata = json.loads(blob.download_as_text())
                        if (query in metadata.get("title", "").lower() or 
                            query in metadata.get("description", "").lower()):
                            results.append(metadata)
        else:
            # Поиск для конкретного пользователя
            blobs = bucket.list_blobs(prefix=prefix)
            
            for blob in blobs:
                if blob.name.endswith('.json'):
                    metadata = json.loads(blob.download_as_text())
                    if (query in metadata.get("title", "").lower() or 
                        query in metadata.get("description", "").lower()):
                        results.append(metadata)
        
        return results
    
    except Exception as e:
        logger.error(f"Error searching videos: {e}")
        return []