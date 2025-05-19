import os
import json
import sys
import datetime

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eduvideo.settings')
import django
django.setup()

from main.s3_storage import get_bucket, BUCKET_NAME

def inspect_s3_structure():
    """
    Анализирует структуру S3 и выводит данные о пользователях и видео
    """
    print("\n" + "="*50)
    print("АНАЛИЗ СТРУКТУРЫ S3")
    print("="*50)
    
    bucket = get_bucket(BUCKET_NAME)
    if not bucket:
        print(f"Ошибка: Не удалось получить доступ к бакету {BUCKET_NAME}")
        return
    
    client = bucket['client']
    bucket_name = bucket['name']
    
    print(f"Успешное подключение к бакету: {bucket_name}")
    
    # Получаем список пользователей через получение "директорий" верхнего уровня
    users = set()
    result = client.list_objects_v2(Bucket=bucket_name, Delimiter='/')
    
    # Получаем все префиксы (папки)
    for prefix in result.get('CommonPrefixes', []):
        user_id = prefix.get('Prefix', '').rstrip('/')
        if user_id and user_id.startswith('@'):
            users.add(user_id)
    
    print(f"\nНайдено пользователей: {len(users)}")
    for user in users:
        print(f"  {user}")
    
    total_videos = 0
    total_metadata = 0
    
    # Анализируем каждого пользователя
    for user_id in users:
        print(f"\n{'-'*30}")
        print(f"Пользователь: {user_id}")
        print(f"{'-'*30}")
        
        # Проверяем профиль пользователя
        user_meta_key = f"{user_id}/bio/user_meta.json"
        try:
            client.head_object(Bucket=bucket_name, Key=user_meta_key)
            try:
                response = client.get_object(Bucket=bucket_name, Key=user_meta_key)
                user_profile = json.loads(response['Body'].read().decode('utf-8'))
                print(f"Профиль: {user_profile.get('display_name', 'Имя не указано')}")
            except Exception as e:
                print(f"Ошибка чтения профиля: {e}")
        except Exception:
            print("Профиль не найден")
        
        # Ищем видео пользователя
        metadata_prefix = f"{user_id}/metadata/"
        
        # Используем пагинатор для получения всех объектов с данным префиксом
        paginator = client.get_paginator('list_objects_v2')
        metadata_objects = []
        
        pages = paginator.paginate(Bucket=bucket_name, Prefix=metadata_prefix)
        for page in pages:
            if 'Contents' in page:
                metadata_objects.extend(page['Contents'])
        
        print(f"Найдено метаданных видео: {len(metadata_objects)}")
        total_metadata += len(metadata_objects)
        
        # Анализируем метаданные
        videos = []
        for obj in metadata_objects:
            if obj['Key'].endswith('.json'):
                try:
                    response = client.get_object(Bucket=bucket_name, Key=obj['Key'])
                    metadata = json.loads(response['Body'].read().decode('utf-8'))
                    videos.append(metadata)
                    print(f"  - {metadata.get('video_id')}: {metadata.get('title', 'Без названия')}")
                    
                    # Проверяем наличие миниатюры
                    if 'thumbnail_path' in metadata:
                        try:
                            client.head_object(Bucket=bucket_name, Key=metadata['thumbnail_path'])
                            print(f"    ✓ Миниатюра найдена: {metadata['thumbnail_path']}")
                        except Exception:
                            print(f"    ✗ Миниатюра не найдена: {metadata['thumbnail_path']}")
                    else:
                        print(f"    ✗ Путь к миниатюре не указан в метаданных")
                        
                    # Проверяем наличие самого видео
                    if 'file_path' in metadata:
                        try:
                            client.head_object(Bucket=bucket_name, Key=metadata['file_path'])
                            print(f"    ✓ Видеофайл найден: {metadata['file_path']}")
                        except Exception:
                            print(f"    ✗ Видеофайл не найден: {metadata['file_path']}")
                    else:
                        print(f"    ✗ Путь к видео не указан в метаданных")
                except Exception as e:
                    print(f"  ✗ Ошибка обработки {obj['Key']}: {e}")
        
        total_videos += len(videos)
    
    print("\n" + "="*50)
    print(f"ИТОГО:")
    print(f"  Пользователей: {len(users)}")
    print(f"  Метаданных видео: {total_metadata}")
    print(f"  Обработанных видео: {total_videos}")
    print("="*50)

if __name__ == "__main__":
    inspect_s3_structure()