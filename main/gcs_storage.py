from google.cloud import storage
import os
import json
from datetime import datetime
from django.conf import settings

def find_json_file(start_dir=None, filename_part="kronik-26102005-6949b1ae3add.json"):
    """
    Расширенный поиск JSON-файла с ключом для Google Cloud
    
    Args:
        start_dir (str, optional): Начальная директория для поиска. 
                                   Если None, будет использован текущий проект.
        filename_part (str): Часть имени файла для поиска
    
    Returns:
        str: Полный путь к найденному файлу или None
    """
    import os
    from django.conf import settings
    
    # Список возможных директорий для поиска
    search_dirs = [
        os.getcwd(),  # Текущая рабочая директория
        settings.BASE_DIR,  # Корень Django-проекта
        os.path.join(settings.BASE_DIR, 'config'),  # Папка конфигурации
        os.path.join(settings.BASE_DIR, 'credentials'),  # Папка с credentials
        os.path.join(settings.BASE_DIR, 'keys'),  # Папка с ключами
    ]
    
    # Если передана конкретная стартовая директория
    if start_dir:
        search_dirs.insert(0, start_dir)
    
    # Расширенный поиск файла
    for root_dir in search_dirs:
        for root, dirs, files in os.walk(root_dir):
            matching_files = [
                os.path.join(root, file) 
                for file in files 
                if filename_part in file and file.endswith('.json')
            ]
            
            if matching_files:
                print(f"✅ Найден JSON-файл: {matching_files[0]}")
                return matching_files[0]
    
    print("❌ JSON-файл для Google Cloud не найден!")
    return None

def init_gcs_client():
    """
    Инициализирует клиент Google Cloud Storage с расширенным поиском ключа
    """
    try:
        # Пытаемся найти ключ
        credentials_path = find_json_file()
        
        if not credentials_path:
            # Если ключ не найден, пробуем использовать стандартную аутентификацию
            from google.cloud import storage
            return storage.Client()
        
        # Устанавливаем путь к ключу
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        # Инициализируем клиент
        from google.cloud import storage
        client = storage.Client()
        return client
    
    except Exception as e:
        print(f"❌ Ошибка при инициализации клиента GCS: {e}")
        return None
    
BUCKET_NAME = "kronik-portage"

def create_bucket(bucket_name=BUCKET_NAME, storage_class="STANDARD", location="US"):
    """Создаёт бакет в Google Cloud Storage"""
    try:
        # Инициализируем клиент с учетом нового пути к учетным данным
        client = init_gcs_client()
        if not client:
            raise Exception("Не удалось инициализировать клиент GCS")

        # Проверяем, существует ли бакет
        if client.bucket(bucket_name).exists():
            print(f"ℹ️ Бакет {bucket_name} уже существует")
            return client.bucket(bucket_name)

        # Создаём бакет
        bucket = client.bucket(bucket_name)
        bucket.storage_class = storage_class  # Класс хранения (STANDARD, NEARLINE и т. д.)
        new_bucket = client.create_bucket(bucket, location=location)

        print(f"✅ Бакет {new_bucket.name} создан в регионе {new_bucket.location}")
        return new_bucket
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def connect_to_gcs():
    """ Подключается к Google Cloud Storage и выводит список бакетов """
    try:
        client = storage.Client()
        buckets = list(client.list_buckets())
        
        if not buckets:
            print("Нет доступных бакетов")
        else:
            print("Доступные бакеты:")
            for bucket in buckets:
                print(f"- {bucket.name}")
        
        return client
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

def get_bucket(bucket_name=BUCKET_NAME):
    """Получает бакет по имени, создает если не существует"""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    
    if not bucket.exists():
        return create_bucket(bucket_name)
    
    return bucket

def create_user_folder_structure(user_id):
    """Создает структуру папок для пользователя"""
    folder_types = ["videos", "thumbnails", "metadata", "comments"]
    bucket = get_bucket()
    
    for folder_type in folder_types:
        folder_path = f"{user_id}/{folder_type}/"
        blob = bucket.blob(folder_path)
        if not blob.exists():
            # Создаем пустой файл как маркер папки (GCS не имеет реальных папок)
            blob = bucket.blob(f"{folder_path}.keep")
            blob.upload_from_string('')
            print(f"✅ Создана папка {folder_path}")
    
    print(f"✅ Структура папок для пользователя {user_id} создана успешно")

def upload_video(user_id, video_file_path, title=None, description=None):
    """
    Загружает видеофайл в хранилище и создает соответствующие метаданные
    
    Parameters:
    - user_id: ID пользователя
    - video_file_path: Путь к видеофайлу на локальном компьютере
    - title: Название видео (опционально)
    - description: Описание видео (опционально)
    
    Returns:
    - video_id: ID видео в формате даты и имени файла
    """
    bucket = get_bucket()
    
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
        
        print(f"✅ Видео {video_id} успешно загружено")
        return video_id
    
    except Exception as e:
        print(f"❌ Ошибка при загрузке видео: {e}")
        return None

def upload_thumbnail(user_id, video_id, thumbnail_file_path):
    """Загружает миниатюру для видео"""
    bucket = get_bucket()
    
    file_extension = os.path.splitext(thumbnail_file_path)[1]
    thumbnail_path = f"{user_id}/thumbnails/{video_id}{file_extension}"
    
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
        
        print(f"✅ Миниатюра для видео {video_id} успешно загружена")
        return True
    
    except Exception as e:
        print(f"❌ Ошибка при загрузке миниатюры: {e}")
        return False

def add_comment(user_id, video_id, comment_user_id, comment_text):
    """Добавляет комментарий к видео"""
    bucket = get_bucket()
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
        
        print(f"✅ Комментарий добавлен к видео {video_id}")
        return True
    
    except Exception as e:
        print(f"❌ Ошибка при добавлении комментария: {e}")
        return False

def get_video_metadata(user_id, video_id):
    """Получает метаданные видео"""
    bucket = get_bucket()
    metadata_path = f"{user_id}/metadata/{video_id}.json"
    
    try:
        metadata_blob = bucket.blob(metadata_path)
        
        if metadata_blob.exists():
            return json.loads(metadata_blob.download_as_text())
        else:
            print(f"❌ Метаданные для видео {video_id} не найдены")
            return None
    
    except Exception as e:
        print(f"❌ Ошибка при получении метаданных: {e}")
        return None

def get_video_comments(user_id, video_id):
    """Получает комментарии к видео"""
    bucket = get_bucket()
    comments_path = f"{user_id}/comments/{video_id}_comments.json"
    
    try:
        comments_blob = bucket.blob(comments_path)
        
        if comments_blob.exists():
            return json.loads(comments_blob.download_as_text())
        else:
            print(f"❌ Комментарии для видео {video_id} не найдены")
            return {"comments": []}
    
    except Exception as e:
        print(f"❌ Ошибка при получении комментариев: {e}")
        return {"comments": []}

def download_video(user_id, video_id, destination_folder="."):
    """Скачивает видео на локальный компьютер"""
    metadata = get_video_metadata(user_id, video_id)
    
    if not metadata or "file_path" not in metadata:
        print(f"❌ Не удалось найти информацию о видео {video_id}")
        return False
    
    bucket = get_bucket()
    video_blob = bucket.blob(metadata["file_path"])
    
    if not video_blob.exists():
        print(f"❌ Видеофайл не найден в хранилище")
        return False
    
    file_extension = os.path.splitext(metadata["file_path"])[1]
    destination_path = os.path.join(destination_folder, f"{video_id}{file_extension}")
    
    try:
        video_blob.download_to_filename(destination_path)
        print(f"✅ Видео {video_id} скачано в {destination_path}")
        return destination_path
    
    except Exception as e:
        print(f"❌ Ошибка при скачивании видео: {e}")
        return False

def increment_view_count(user_id, video_id):
    """Увеличивает счетчик просмотров видео"""
    bucket = get_bucket()
    metadata_path = f"{user_id}/metadata/{video_id}.json"
    
    try:
        metadata_blob = bucket.blob(metadata_path)
        
        if metadata_blob.exists():
            metadata = json.loads(metadata_blob.download_as_text())
            metadata["views"] = metadata.get("views", 0) + 1
            metadata_blob.upload_from_string(json.dumps(metadata, indent=2), content_type='application/json')
            print(f"✅ Счетчик просмотров для видео {video_id} увеличен: {metadata['views']}")
            return metadata["views"]
        else:
            print(f"❌ Метаданные для видео {video_id} не найдены")
            return None
    
    except Exception as e:
        print(f"❌ Ошибка при обновлении счетчика просмотров: {e}")
        return None

def list_user_videos(user_id):
    """Возвращает список всех видео пользователя"""
    bucket = get_bucket()
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
        print(f"❌ Ошибка при получении списка видео: {e}")
        return []

def delete_video(user_id, video_id):
    """Удаляет видео и все связанные файлы"""
    bucket = get_bucket()
    
    # Получаем метаданные для определения путей файлов
    metadata = get_video_metadata(user_id, video_id)
    
    if not metadata:
        print(f"❌ Метаданные для видео {video_id} не найдены, удаление невозможно")
        return False
    
    try:
        # Удаляем файл видео
        if "file_path" in metadata:
            video_blob = bucket.blob(metadata["file_path"])
            if video_blob.exists():
                video_blob.delete()
                print(f"✅ Видеофайл {video_id} удален")
        
        # Удаляем миниатюру
        if "thumbnail_path" in metadata:
            thumbnail_blob = bucket.blob(metadata["thumbnail_path"])
            if thumbnail_blob.exists():
                thumbnail_blob.delete()
                print(f"✅ Миниатюра видео {video_id} удалена")
        
        # Удаляем метаданные
        metadata_path = f"{user_id}/metadata/{video_id}.json"
        metadata_blob = bucket.blob(metadata_path)
        if metadata_blob.exists():
            metadata_blob.delete()
            print(f"✅ Метаданные видео {video_id} удалены")
        
        # Удаляем комментарии
        comments_path = f"{user_id}/comments/{video_id}_comments.json"
        comments_blob = bucket.blob(comments_path)
        if comments_blob.exists():
            comments_blob.delete()
            print(f"✅ Комментарии к видео {video_id} удалены")
        
        print(f"✅ Видео {video_id} и все связанные файлы успешно удалены")
        return True
    
    except Exception as e:
        print(f"❌ Ошибка при удалении видео: {e}")
        return False

def get_user_storage_usage(user_id):
    """Возвращает информацию об использовании хранилища пользователем"""
    bucket = get_bucket()
    user_prefix = f"{user_id}/"
    
    total_size = 0
    file_counts = {
        "videos": 0,
        "thumbnails": 0,
        "metadata": 0,
        "comments": 0
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
        print(f"❌ Ошибка при получении информации об использовании хранилища: {e}")
        return None

def generate_video_url(user_id, video_id, expiration_time=3600):
    """Генерирует временную URL-ссылку для доступа к видео"""
    metadata = get_video_metadata(user_id, video_id)
    
    if not metadata or "file_path" not in metadata:
        print(f"❌ Не удалось найти информацию о видео {video_id}")
        return None
    
    bucket = get_bucket()
    video_blob = bucket.blob(metadata["file_path"])
    
    if not video_blob.exists():
        print(f"❌ Видеофайл не найден в хранилище")
        return None
    
    try:
        url = video_blob.generate_signed_url(
            version="v4",
            expiration=expiration_time,
            method="GET"
        )
        
        print(f"✅ Сгенерирована временная ссылка на видео {video_id} (действительна {expiration_time} секунд)")
        return url
    
    except Exception as e:
        print(f"❌ Ошибка при генерации ссылки: {e}")
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
        print(f"❌ Ошибка при поиске видео: {e}")
        return []

# Пример использования
if __name__ == "__main__":
    # Создаём бакет
    create_bucket()
    
    # Создаём структуру папок для пользователя
    user_id = "user123"
    # create_user_folder_structure(user_id)
    
    # # Пример загрузки видео (требуется указать локальный путь к файлу)
    # video_path = "video.mp4"
    # video_id = upload_video(user_id, video_path, "Моё тестовое видео", "Это описание видео")
    
    # # # Пример загрузки миниатюры
    # thumbnail_path = "thumbnail.jpg"
    # upload_thumbnail(user_id, video_id, thumbnail_path)
    
    # # # Получение метаданных
    # metadata = get_video_metadata(user_id, video_id)
    # print("Метаданные видео:", metadata)
    
    # # # Добавление комментария
    # add_comment(user_id, video_id, "viewer1", "Отличное видео!")
    
    # # # Получение комментариев
    # comments = get_video_comments(user_id, video_id)
    # print("Комментарии к видео:", comments)
    
    # # # Увеличение счетчика просмотров
    # increment_view_count(user_id, video_id)
    
    # # # Получение списка всех видео пользователя
    # videos = list_user_videos(user_id)
    # print(f"Всего видео пользователя {user_id}: {len(videos)}")
    
    # # # Генерация временной ссылки
    # url = generate_video_url(user_id, video_id)
    # print("Временная ссылка на видео:", url)