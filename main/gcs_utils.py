from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from .gcs_storage import init_gcs_client, get_bucket, BUCKET_NAME
import logging

# Set up logging
logger = logging.getLogger(__name__)

def create_user_folder_structure(username):
    """
    Creates the folder structure for a new user in Google Cloud Storage.
    
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
            
        folder_types = ["videos", "previews", "metadata", "comments", "bio"]
        
        for folder_type in folder_types:
            folder_path = f"{username}/{folder_type}/"
            blob = bucket.blob(folder_path)
            
            marker_blob = bucket.blob(f"{folder_path}.keep")
            marker_blob.upload_from_string('')
            logger.info(f"Created folder {folder_path} for user {username}")
            
        welcome_path = f"{username}/bio/welcome.txt"
        welcome_blob = bucket.blob(welcome_path)
        welcome_message = f"Welcome to KRONIK, {username}! This is your personal storage space."
        welcome_blob.upload_from_string(welcome_message)
        
        logger.info(f"Successfully created folder structure for user {username}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating folder structure for user {username}: {str(e)}")
        return False

@receiver(post_save, sender=User)
def create_user_gcs_folders(sender, instance, created, **kwargs):
    """
    Signal handler to create GCS folders when a user is created.
    Preserves the @ prefix in the username.
    """
    if created:
        username = instance.username
        logger.info(f"New user created: {username}. Creating GCS folder structure...")
        create_user_folder_structure(username)