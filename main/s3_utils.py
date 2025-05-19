"""
S3 utility functions for Django application
"""
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from .s3_storage import init_s3_client, get_bucket, BUCKET_NAME, update_user_profile_in_gcs
import logging
import os
from django.conf import settings

# Set up logging
logger = logging.getLogger(__name__)

def create_user_folder_structure(username):
    """
    Creates the folder structure for a new user in S3-compatible storage.
    Also uploads a default avatar image.
    
    Args:
        username (str): The username of the user (with '@' prefix)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        bucket = get_bucket(BUCKET_NAME)
        if not bucket:
            logger.error(f"Could not get bucket {BUCKET_NAME} for user {username}")
            return False
            
        client = bucket['client']
        bucket_name = bucket['name']
        
        folder_types = ["videos", "previews", "metadata", "comments", "bio"]
        
        for folder_type in folder_types:
            folder_path = f"{username}/{folder_type}/"
            
            # Create a marker object for each folder
            marker_key = f"{folder_path}.keep"
            client.put_object(
                Bucket=bucket_name,
                Key=marker_key,
                Body=''
            )
            logger.info(f"Created folder {folder_path} for user {username}")
            
        # Create welcome file
        welcome_path = f"{username}/bio/welcome.txt"
        welcome_message = f"Welcome to KRONIK, {username}! This is your personal storage space."
        client.put_object(
            Bucket=bucket_name,
            Key=welcome_path,
            Body=welcome_message,
            ContentType='text/plain'
        )
        
        # Add user_meta.json file
        user_meta_path = f"{username}/bio/user_meta.json"
        import json
        from datetime import datetime
        user_meta = {
            "user_id": username,
            "created_at": datetime.now().isoformat(),
            "display_name": "",
            "avatar_path": f"{username}/bio/default_avatar.png",  # Set default avatar path
            "is_default_avatar": True,
            "stats": {
                "videos_count": 0,
                "total_views": 0
            }
        }
        client.put_object(
            Bucket=bucket_name,
            Key=user_meta_path,
            Body=json.dumps(user_meta, indent=2),
            ContentType='application/json'
        )
        
        # Upload default avatar
        default_avatar_path = os.path.join(settings.STATIC_ROOT, 'default.png')
        if not os.path.exists(default_avatar_path):
            default_avatar_path = os.path.join(settings.BASE_DIR, 'static', 'default.png')
        
        if os.path.exists(default_avatar_path):
            avatar_blob_path = f"{username}/bio/default_avatar.png"
            from .s3_storage import mimetypes
            mime_type = mimetypes.guess_type(default_avatar_path)[0] or 'image/png'
            
            with open(default_avatar_path, 'rb') as file_data:
                client.put_object(
                    Bucket=bucket_name,
                    Key=avatar_blob_path,
                    Body=file_data,
                    ContentType=mime_type
                )
            logger.info(f"Default avatar uploaded for user {username}")
        else:
            logger.warning(f"Default avatar file not found at {default_avatar_path}")
        
        logger.info(f"Successfully created folder structure for user {username}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating folder structure for user {username}: {str(e)}")
        return False

@receiver(post_save, sender=User)
def create_user_s3_folders(sender, instance, created, **kwargs):
    """
    Signal handler to create S3 folders when a user is created.
    Preserves the @ prefix in the username.
    """
    if created:
        username = instance.username
        logger.info(f"New user created: {username}. Creating S3 folder structure...")
        create_user_folder_structure(username)