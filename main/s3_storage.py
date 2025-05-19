import boto3
import os
import json
from datetime import datetime, timedelta
from django.conf import settings
import logging
import mimetypes
import uuid
import ffmpeg

# Set up logging
logger = logging.getLogger(__name__)
BUCKET_NAME = "kronik-portage"  # Keep original bucket name for compatibility

def init_s3_client():
    """Initialize S3 client with Cloudpard credentials"""
    try:
        client = boto3.client(
            's3',
            endpoint_url='https://storage.cloupard.uz',
            aws_access_key_id='RQCV6OIXPPW3CIUPD41M',
            aws_secret_access_key='41rvd+2JvErImMVU529tPICoLNe6O1NGrrKzWvzv'
        )
        return client
    except Exception as e:
        logger.error(f"Error initializing S3 client: {e}")
        return None

def get_bucket(bucket_name=BUCKET_NAME):
    """
    Get a bucket reference. In S3, we don't have a specific bucket object like in GCS,
    but this function maintains API compatibility with the original code.
    """
    try:
        client = init_s3_client()
        if not client:
            raise Exception("Failed to initialize S3 client")
            
        # Check if bucket exists by listing buckets
        response = client.list_buckets()
        bucket_exists = False
        
        for bucket in response['Buckets']:
            if bucket['Name'] == bucket_name:
                bucket_exists = True
                break
                
        if not bucket_exists:
            logger.error(f"Bucket {bucket_name} does not exist")
            return None
            
        # For diagnostic logging, list objects in the bucket
        try:
            response = client.list_objects_v2(Bucket=bucket_name, MaxKeys=100)
            objects = response.get('Contents', [])
            logger.info(f"Total objects in bucket: {len(objects)}")
            
            # Log first 10 object names
            object_names = [obj['Key'] for obj in objects[:10]]
            logger.info(f"First 10 object names: {object_names}")
            
            # Try to find unique top-level folders
            folders = set()
            for obj in objects:
                parts = obj['Key'].split('/')
                if parts and parts[0]:
                    folders.add(parts[0])
            
            logger.info(f"Unique top-level folders: {folders}")
        except Exception as diag_error:
            logger.error(f"Error during bucket diagnostic logging: {diag_error}")
        
        logger.info(f"Successfully accessed bucket: {bucket_name}")
        
        # Return a "bucket" proxy object that includes the client and name
        # for compatibility with the original code
        return {
            'client': client,
            'name': bucket_name
        }
    except Exception as e:
        logger.error(f"Error getting bucket: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def update_video_metadata(user_id, video_id, metadata):
    """Update metadata JSON file in S3"""
    try:
        bucket = get_bucket()
        if not bucket:
            return False
            
        client = bucket['client']
        bucket_name = bucket['name']
        metadata_path = f"{user_id}/metadata/{video_id}.json"
        
        # Check if object exists
        try:
            client.head_object(Bucket=bucket_name, Key=metadata_path)
        except Exception:
            return False
            
        # Upload updated metadata
        client.put_object(
            Bucket=bucket_name,
            Key=metadata_path,
            Body=json.dumps(metadata, indent=2),
            ContentType='application/json'
        )
        return True
    except Exception as e:
        logger.error(f"Error updating video metadata for {user_id}/{video_id}: {e}")
        return False

def create_user_folder_structure(user_id):
    """
    Creates the folder structure for a user.
    
    Args:
        user_id (str): Username (with @ prefix)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        bucket = get_bucket()
        if not bucket:
            logger.error(f"Could not get bucket for user {user_id}")
            return False
            
        client = bucket['client']
        bucket_name = bucket['name']
        
        # Determine folder types to create
        folder_types = ["videos", "previews", "metadata", "comments", "bio"]
        
        for folder_type in folder_types:
            folder_path = f"{user_id}/{folder_type}/"
            
            # Create a marker object to represent the folder (S3 doesn't have real folders)
            marker_key = f"{folder_path}.keep"
            client.put_object(
                Bucket=bucket_name,
                Key=marker_key,
                Body=''
            )
            logger.info(f"Created folder {folder_path}")
        
        # Create initial empty user files
        init_user_files(user_id, bucket)
        
        # Upload default avatar
        default_avatar_path = os.path.join(settings.STATIC_ROOT, 'default.png')
        if not os.path.exists(default_avatar_path):
            default_avatar_path = os.path.join(settings.BASE_DIR, 'static', 'default.png')
        
        if os.path.exists(default_avatar_path):
            avatar_blob_path = f"{user_id}/bio/default_avatar.png"
            mime_type = mimetypes.guess_type(default_avatar_path)[0] or 'image/png'
            
            with open(default_avatar_path, 'rb') as file_data:
                client.put_object(
                    Bucket=bucket_name,
                    Key=avatar_blob_path,
                    Body=file_data,
                    ContentType=mime_type
                )
            logger.info(f"Default avatar uploaded for user {user_id}")
        
        logger.info(f"Successfully created folder structure for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating folder structure for user {user_id}: {str(e)}")
        return False

def init_user_files(user_id, bucket):
    """Initialize important user files"""
    try:
        client = bucket['client']
        bucket_name = bucket['name']
        
        # Create empty user metadata
        user_meta = {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "display_name": "",
            "avatar_path": f"{user_id}/bio/default_avatar.png",  # Set default avatar path
            "is_default_avatar": True,
            "stats": {
                "videos_count": 0,
                "total_views": 0
            }
        }
        
        # Save user metadata
        meta_key = f"{user_id}/bio/user_meta.json"
        client.put_object(
            Bucket=bucket_name,
            Key=meta_key,
            Body=json.dumps(user_meta, indent=2),
            ContentType='application/json'
        )
        
        # Create welcome file
        welcome_key = f"{user_id}/bio/welcome.txt"
        welcome_message = f"Welcome to KRONIK, {user_id}! This is your personal storage space."
        client.put_object(
            Bucket=bucket_name,
            Key=welcome_key,
            Body=welcome_message,
            ContentType='text/plain'
        )
        
        return True
    except Exception as e:
        logger.error(f"Error initializing user files for {user_id}: {e}")
        return False

def upload_video(user_id, video_file_path, title=None, description=None):
    """
    Upload a video file to storage and create corresponding metadata
    
    Parameters:
    - user_id: User ID or username (with @ prefix)
    - video_file_path: Path to the video file on the local computer
    - title: Video title (optional)
    - description: Video description (optional)
    
    Returns:
    - video_id: Video ID in the format of date and filename
    """
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for video upload")
        return None
    
    client = bucket['client']
    bucket_name = bucket['name']
    
    # Create folder structure if it doesn't exist
    # Just check if essential folders exist
    try:
        folder_types = ["videos", "previews", "metadata", "comments"]
        
        for folder_type in folder_types:
            folder_path = f"{user_id}/{folder_type}/"
            marker_key = f"{folder_path}.keep"
            
            try:
                client.head_object(Bucket=bucket_name, Key=marker_key)
            except:
                # If marker doesn't exist, create it
                client.put_object(
                    Bucket=bucket_name,
                    Key=marker_key,
                    Body=''
                )
                logger.info(f"Created missing folder {folder_path}")
    except Exception as e:
        logger.error(f"Error checking/creating folders for video upload: {e}")
        # Continue anyway as we'll check individual paths
    
    # Generate video ID based on date and filename
    now = datetime.now()
    date_prefix = now.strftime("%Y-%m-%d")
    
    # Get filename from path
    file_name = os.path.basename(video_file_path)
    base_name = os.path.splitext(file_name)[0]
    file_extension = os.path.splitext(file_name)[1]
    
    # Form video ID
    video_id = f"{date_prefix}_{base_name}"
    
    # Form paths for storage
    video_path = f"{user_id}/videos/{video_id}{file_extension}"
    metadata_path = f"{user_id}/metadata/{video_id}.json"
    comments_path = f"{user_id}/comments/{video_id}_comments.json"
    
    try:
        # Get file size and MIME type
        file_size = os.path.getsize(video_file_path)
        mime_type = mimetypes.guess_type(video_file_path)[0] or 'video/mp4'
        
        # Extract video duration if possible
        duration = get_video_duration(video_file_path)
        
        # Upload video
        with open(video_file_path, 'rb') as file_data:
            client.put_object(
                Bucket=bucket_name,
                Key=video_path,
                Body=file_data,
                ContentType=mime_type
            )
        
        # Create metadata
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
            "duration": duration,
            "status": "published"
        }
        
        # Save metadata
        client.put_object(
            Bucket=bucket_name,
            Key=metadata_path,
            Body=json.dumps(metadata, indent=2),
            ContentType='application/json'
        )
        
        # Create empty comments file
        comments = {
            "video_id": video_id,
            "comments": []
        }
        client.put_object(
            Bucket=bucket_name,
            Key=comments_path,
            Body=json.dumps(comments, indent=2),
            ContentType='application/json'
        )
        
        # Update user stats
        update_user_stats(user_id, bucket)
        
        logger.info(f"Video {video_id} successfully uploaded")
        return video_id
    
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        return None

def get_video_duration(video_file_path):
    """
    Extracts duration from video file using locally installed ffmpeg binary
    """
    try:
        import subprocess
        import os
        import json
        from django.conf import settings
        
        ffmpeg_dir = os.path.join(settings.BASE_DIR, 'ffmpeg')
        
        if os.name == 'nt':
            ffprobe_path = os.path.join(ffmpeg_dir, 'bin', 'ffprobe.exe')
        else:
            ffprobe_path = os.path.join(ffmpeg_dir, 'bin', 'ffprobe')
        
        if not os.path.exists(ffprobe_path):
            logger.error(f"ffprobe not found at {ffprobe_path}")
            raise FileNotFoundError(f"ffprobe not found at {ffprobe_path}")
        
        cmd = [
            ffprobe_path,
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json',
            video_file_path
        ]
        
        logger.info(f"Executing ffprobe: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"ffprobe error: {result.stderr}")
            raise Exception(f"ffprobe exited with code {result.returncode}: {result.stderr}")
        
        output_data = json.loads(result.stdout)
        duration_seconds = float(output_data['format']['duration'])
        
        minutes = int(duration_seconds // 60)
        seconds = int(duration_seconds % 60)
        formatted_duration = f"{minutes:02d}:{seconds:02d}"
        
        logger.info(f"Extracted video duration: {formatted_duration}")
        return formatted_duration
        
    except Exception as e:
        logger.error(f"Could not extract video duration with ffmpeg: {e}")
        
        # Fallback to random duration
        import random
        minutes = random.randint(3, 15)
        seconds = random.randint(0, 59)
        random_duration = f"{minutes:02d}:{seconds:02d}"
        logger.info(f"Using random duration as fallback: {random_duration}")
        return random_duration

def update_user_stats(user_id, bucket=None):
    """Updates user statistics in metadata"""
    if not bucket:
        bucket = get_bucket()
        if not bucket:
            return False
    
    try:
        client = bucket['client']
        bucket_name = bucket['name']
        
        # Get user metadata
        user_meta_path = f"{user_id}/bio/user_meta.json"
        
        try:
            response = client.get_object(Bucket=bucket_name, Key=user_meta_path)
            user_meta = json.loads(response['Body'].read().decode('utf-8'))
        except Exception:
            # If metadata doesn't exist, create default
            user_meta = {
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "stats": {}
            }
        
        # Count videos
        videos_list = list_user_videos(user_id, bucket)
        videos_count = len(videos_list)
        
        # Calculate total views
        total_views = sum(video.get('views', 0) for video in videos_list)
        
        # Update statistics
        if "stats" not in user_meta:
            user_meta["stats"] = {}
            
        user_meta["stats"]["videos_count"] = videos_count
        user_meta["stats"]["total_views"] = total_views
        user_meta["last_updated"] = datetime.now().isoformat()
        
        # Save updated metadata
        client.put_object(
            Bucket=bucket_name,
            Key=user_meta_path,
            Body=json.dumps(user_meta, indent=2),
            ContentType='application/json'
        )
        return True
        
    except Exception as e:
        logger.error(f"Error updating user stats: {e}")
        return False

def upload_thumbnail(user_id, video_id, thumbnail_file_path):
    """Upload a thumbnail for a video"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for thumbnail upload")
        return False
    
    client = bucket['client']
    bucket_name = bucket['name']
    
    file_extension = os.path.splitext(thumbnail_file_path)[1]
    thumbnail_path = f"{user_id}/previews/{video_id}{file_extension}"
    
    try:
        # Determine MIME type
        mime_type = mimetypes.guess_type(thumbnail_file_path)[0] or 'image/jpeg'
        
        logger.info(f"Uploading thumbnail for video {video_id} from {thumbnail_file_path} to {thumbnail_path}")
        
        # Upload thumbnail
        with open(thumbnail_file_path, 'rb') as file_data:
            client.put_object(
                Bucket=bucket_name,
                Key=thumbnail_path,
                Body=file_data,
                ContentType=mime_type
            )
        
        # Update metadata with thumbnail information
        metadata_path = f"{user_id}/metadata/{video_id}.json"
        
        try:
            response = client.get_object(Bucket=bucket_name, Key=metadata_path)
            metadata_content = json.loads(response['Body'].read().decode('utf-8'))
            
            metadata_content["thumbnail_path"] = thumbnail_path
            metadata_content["thumbnail_mime_type"] = mime_type
            
            client.put_object(
                Bucket=bucket_name,
                Key=metadata_path,
                Body=json.dumps(metadata_content, indent=2),
                ContentType='application/json'
            )
            logger.info(f"Updated metadata with thumbnail path: {thumbnail_path}")
        except Exception as e:
            logger.error(f"Metadata not found for video {video_id}: {e}")
        
        logger.info(f"Thumbnail for video {video_id} successfully uploaded")
        return True
    
    except Exception as e:
        logger.error(f"Error uploading thumbnail: {e}")
        return False

def add_comment(user_id, video_id, comment_user_id, comment_text, display_name=None, avatar_url=None):
    """Add a comment to a video with avatar URL support"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for adding comment")
        return False
        
    client = bucket['client']
    bucket_name = bucket['name']
    comments_path = f"{user_id}/comments/{video_id}_comments.json"
    
    try:
        try:
            response = client.get_object(Bucket=bucket_name, Key=comments_path)
            comments_data = json.loads(response['Body'].read().decode('utf-8'))
        except Exception:
            comments_data = {"comments": []}
        
        # Generate unique comment ID
        comment_id = str(uuid.uuid4())
        
        # Add new comment with avatar URL
        new_comment = {
            "id": comment_id,
            "user_id": comment_user_id,
            "display_name": display_name or comment_user_id,
            "text": comment_text,
            "date": datetime.now().isoformat(),
            "likes": 0,
            "replies": []
        }
        
        # Add avatar URL if provided
        if avatar_url:
            new_comment["avatar_url"] = avatar_url
        
        comments_data["comments"].append(new_comment)
        
        # Save updated comments
        client.put_object(
            Bucket=bucket_name,
            Key=comments_path,
            Body=json.dumps(comments_data, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Comment added to video {video_id}")
        return True
    
    except Exception as e:
        logger.error(f"Error adding comment: {e}")
        return False

def add_reply(user_id, video_id, comment_id, reply_user_id, reply_text, display_name=None, avatar_url=None):
    """Add a reply to a comment with avatar URL support"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for adding reply")
        return False
        
    client = bucket['client']
    bucket_name = bucket['name']
    comments_path = f"{user_id}/comments/{video_id}_comments.json"
    
    try:
        try:
            response = client.get_object(Bucket=bucket_name, Key=comments_path)
            comments_data = json.loads(response['Body'].read().decode('utf-8'))
        except Exception:
            logger.error(f"Comments file not found for video {video_id}")
            return False
            
        # Find the comment to reply to
        found = False
        for comment in comments_data.get("comments", []):
            if comment.get("id") == comment_id:
                # Generate unique reply ID
                reply_id = str(uuid.uuid4())
                
                # Create reply object with avatar URL
                reply = {
                    "id": reply_id,
                    "user_id": reply_user_id,
                    "display_name": display_name or reply_user_id,
                    "text": reply_text,
                    "date": datetime.now().isoformat(),
                    "likes": 0
                }
                
                # Add avatar URL if provided
                if avatar_url:
                    reply["avatar_url"] = avatar_url
                
                # Add reply to comment
                if "replies" not in comment:
                    comment["replies"] = []
                    
                comment["replies"].append(reply)
                found = True
                break
        
        if not found:
            logger.error(f"Comment {comment_id} not found in video {video_id}")
            return False
            
        # Save updated comments
        client.put_object(
            Bucket=bucket_name,
            Key=comments_path,
            Body=json.dumps(comments_data, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Reply added to comment {comment_id} in video {video_id}")
        return True
    
    except Exception as e:
        logger.error(f"Error adding reply: {e}")
        return False

def get_video_metadata(user_id, video_id):
    """Get video metadata"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for retrieving metadata")
        return None
        
    client = bucket['client']
    bucket_name = bucket['name']
    metadata_path = f"{user_id}/metadata/{video_id}.json"
    
    try:
        response = client.get_object(Bucket=bucket_name, Key=metadata_path)
        return json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        logger.warning(f"Metadata for video {video_id} not found: {e}")
        return None

def get_video_comments(user_id, video_id):
    """Get comments for a video"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for retrieving comments")
        return {"comments": []}
        
    client = bucket['client']
    bucket_name = bucket['name']
    comments_path = f"{user_id}/comments/{video_id}_comments.json"
    
    try:
        response = client.get_object(Bucket=bucket_name, Key=comments_path)
        return json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        logger.warning(f"Comments for video {video_id} not found: {e}")
        return {"comments": []}

def list_user_videos(user_id, bucket=None):
    """List all videos for a user"""
    if not bucket:
        bucket = get_bucket()
        if not bucket:
            logger.error(f"Could not get bucket for listing videos")
            return []
    
    client = bucket['client']
    bucket_name = bucket['name']
    metadata_prefix = f"{user_id}/metadata/"
    
    videos_list = []
    
    try:
        # List objects with the metadata prefix
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, Prefix=metadata_prefix)
        
        for page in pages:
            for obj in page.get('Contents', []):
                if obj['Key'].endswith('.json'):
                    try:
                        response = client.get_object(Bucket=bucket_name, Key=obj['Key'])
                        metadata = json.loads(response['Body'].read().decode('utf-8'))
                        videos_list.append(metadata)
                    except Exception as e:
                        logger.error(f"Error loading metadata from {obj['Key']}: {e}")
        
        # Sort by upload date (newest first)
        videos_list.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
        
        return videos_list
    
    except Exception as e:
        logger.error(f"Error getting video list: {e}")
        return []

def delete_video(user_id, video_id):
    """Delete a video and all related files"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for deleting video")
        return False
    
    client = bucket['client']
    bucket_name = bucket['name']
    
    # Get metadata to determine file paths
    metadata = get_video_metadata(user_id, video_id)
    
    if not metadata:
        logger.error(f"Metadata for video {video_id} not found, cannot delete")
        return False
    
    try:
        # Delete video file
        if "file_path" in metadata:
            try:
                client.head_object(Bucket=bucket_name, Key=metadata["file_path"])
                client.delete_object(Bucket=bucket_name, Key=metadata["file_path"])
                logger.info(f"Video file {video_id} deleted")
            except Exception as e:
                logger.warning(f"Video file not found for deletion: {e}")
        
        # Delete thumbnail
        if "thumbnail_path" in metadata:
            try:
                client.head_object(Bucket=bucket_name, Key=metadata["thumbnail_path"])
                client.delete_object(Bucket=bucket_name, Key=metadata["thumbnail_path"])
                logger.info(f"Thumbnail for video {video_id} deleted")
            except Exception as e:
                logger.warning(f"Thumbnail not found for deletion: {e}")
        
        # Delete metadata
        metadata_path = f"{user_id}/metadata/{video_id}.json"
        try:
            client.head_object(Bucket=bucket_name, Key=metadata_path)
            client.delete_object(Bucket=bucket_name, Key=metadata_path)
            logger.info(f"Metadata for video {video_id} deleted")
        except Exception as e:
            logger.warning(f"Metadata file not found for deletion: {e}")
        
        # Delete comments
        comments_path = f"{user_id}/comments/{video_id}_comments.json"
        try:
            client.head_object(Bucket=bucket_name, Key=comments_path)
            client.delete_object(Bucket=bucket_name, Key=comments_path)
            logger.info(f"Comments for video {video_id} deleted")
        except Exception as e:
            logger.warning(f"Comments file not found for deletion: {e}")
        
        # Update user statistics after deletion
        update_user_stats(user_id, bucket)
        
        logger.info(f"Video {video_id} and all related files successfully deleted")
        return True
    
    except Exception as e:
        logger.error(f"Error deleting video: {e}")
        return False

def generate_video_url(user_id, video_id, file_path=None, expiration_time=3600):
    """Generate a temporary URL for accessing a video"""
    metadata = get_video_metadata(user_id, video_id)
    
    if not file_path and (not metadata or "file_path" not in metadata):
        logger.error(f"Could not find information about video {video_id}")
        return None
    
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for generating URL")
        return None
        
    client = bucket['client']
    bucket_name = bucket['name']
    
    # Use provided file path or get from metadata
    path_to_use = file_path if file_path else metadata["file_path"]
    
    # Check if object exists
    try:
        client.head_object(Bucket=bucket_name, Key=path_to_use)
    except Exception:
        logger.error(f"File not found in storage at path: {path_to_use}")
        return None
    
    try:
        # Generate presigned URL using boto3
        url = client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': path_to_use
            },
            ExpiresIn=expiration_time
        )
        
        logger.info(f"Generated temporary URL for file (valid for {expiration_time} seconds)")
        return url
    
    except Exception as e:
        logger.error(f"Error generating URL: {e}")
        return None

def update_user_profile_in_gcs(user_id, display_name=None, bio=None, profile_picture_path=None):
    """
    Update user profile information in storage
    
    Parameters:
    - user_id: User ID or username (with @ prefix)
    - display_name: Display name
    - bio: Biography text
    - profile_picture_path: Path to profile picture file (local)
    
    Returns:
    - True if successful, False otherwise
    """
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for updating user profile")
        return False
    
    client = bucket['client']
    bucket_name = bucket['name']
    
    try:
        # Get current user metadata
        user_meta_path = f"{user_id}/bio/user_meta.json"
        
        try:
            response = client.get_object(Bucket=bucket_name, Key=user_meta_path)
            user_meta = json.loads(response['Body'].read().decode('utf-8'))
        except Exception as e:
            # If metadata doesn't exist, create default
            user_meta = {
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
            }
        
        # Update display name if provided
        if display_name:
            user_meta["display_name"] = display_name
        
        # Update biography if provided
        if bio:
            bio_key = f"{user_id}/bio/bio.txt"
            client.put_object(
                Bucket=bucket_name,
                Key=bio_key,
                Body=bio,
                ContentType='text/plain'
            )
            user_meta["has_bio"] = True
        
        # Handle profile picture
        is_default_image = False
        
        # Check if avatar needs to be removed or is default
        if profile_picture_path and 'default.png' in profile_picture_path.lower():
            is_default_image = True
            # If there's an existing custom avatar, delete it
            if "avatar_path" in user_meta and not user_meta.get("is_default_avatar", False):
                try:
                    existing_avatar_key = user_meta["avatar_path"]
                    client.delete_object(Bucket=bucket_name, Key=existing_avatar_key)
                    logger.info(f"Deleted existing avatar for user {user_id}")
                except Exception as e:
                    logger.error(f"Error deleting existing avatar: {e}")
            
            # Set metadata for default avatar
            if os.path.exists(profile_picture_path):
                file_extension = os.path.splitext(profile_picture_path)[1].lower()
                avatar_path = f"{user_id}/bio/default_avatar{file_extension}"
                
                # Upload default profile image
                mime_type = mimetypes.guess_type(profile_picture_path)[0] or 'image/png'
                with open(profile_picture_path, 'rb') as file_data:
                    client.put_object(
                        Bucket=bucket_name,
                        Key=avatar_path,
                        Body=file_data,
                        ContentType=mime_type
                    )
                
                # Update metadata with avatar path
                user_meta["avatar_path"] = avatar_path
                user_meta["is_default_avatar"] = True
        elif profile_picture_path and os.path.exists(profile_picture_path):
            # If a new avatar is uploaded, delete the old one (if exists)
            if "avatar_path" in user_meta:
                try:
                    existing_avatar_key = user_meta["avatar_path"]
                    client.delete_object(Bucket=bucket_name, Key=existing_avatar_key)
                    logger.info(f"Deleted existing avatar for user {user_id}")
                except Exception as e:
                    logger.error(f"Error deleting existing avatar: {e}")
            
            # Upload new avatar
            file_extension = os.path.splitext(profile_picture_path)[1].lower()
            avatar_path = f"{user_id}/bio/avatar{file_extension}"
            
            mime_type = mimetypes.guess_type(profile_picture_path)[0] or 'image/jpeg'
            with open(profile_picture_path, 'rb') as file_data:
                client.put_object(
                    Bucket=bucket_name,
                    Key=avatar_path,
                    Body=file_data,
                    ContentType=mime_type
                )
            
            # Update metadata with avatar path
            user_meta["avatar_path"] = avatar_path
            user_meta["is_default_avatar"] = False
        
        # Update timestamp
        user_meta["last_updated"] = datetime.now().isoformat()
        
        # Save updated metadata
        client.put_object(
            Bucket=bucket_name,
            Key=user_meta_path,
            Body=json.dumps(user_meta, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"User profile for {user_id} successfully updated in storage")
        return True
        
    except Exception as e:
        logger.error(f"Error updating user profile in storage: {e}")
        return False

def get_user_profile_from_gcs(user_id):
    """Get user profile information from storage"""
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for retrieving user profile")
        return None
    
    client = bucket['client']
    bucket_name = bucket['name']
    
    try:
        # Get user metadata
        user_meta_path = f"{user_id}/bio/user_meta.json"
        
        try:
            response = client.get_object(Bucket=bucket_name, Key=user_meta_path)
            user_meta = json.loads(response['Body'].read().decode('utf-8'))
        except Exception:
            logger.warning(f"User metadata not found for {user_id}")
            return None
        
        # Get biography if exists
        bio_key = f"{user_id}/bio/bio.txt"
        try:
            response = client.get_object(Bucket=bucket_name, Key=bio_key)
            user_meta["bio"] = response['Body'].read().decode('utf-8')
        except Exception:
            user_meta["bio"] = ""
        
        # Generate URL for avatar if exists
        if "avatar_path" in user_meta and user_meta["avatar_path"]:
            avatar_key = user_meta["avatar_path"]
            try:
                client.head_object(Bucket=bucket_name, Key=avatar_key)
                user_meta["avatar_url"] = client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': bucket_name,
                        'Key': avatar_key
                    },
                    ExpiresIn=3600*24
                )
            except Exception as e:
                logger.warning(f"Avatar not found for user {user_id}: {e}")
        
        return user_meta
    
    except Exception as e:
        logger.error(f"Error retrieving user profile from storage: {e}")
        return None

def cache_video_metadata():
    """
    Create and update metadata cache for all videos in the system.
    This cache helps quickly load video lists without accessing each file.
    """
    try:
        bucket = get_bucket()
        if not bucket:
            logger.error("Could not get bucket for caching metadata")
            return False
            
        client = bucket['client']
        bucket_name = bucket['name']
        
        # Create system folder for cache if it doesn't exist
        system_folder_key = 'system/.keep'
        client.put_object(Bucket=bucket_name, Key=system_folder_key, Body='')
            
        cache_folder_key = 'system/cache/.keep'
        client.put_object(Bucket=bucket_name, Key=cache_folder_key, Body='')
        
        # Structure to store metadata for all videos
        all_metadata = []
        
        # Get list of users (top-level folders)
        users = set()
        
        # List all objects with delimiter to get top-level folders
        result = client.list_objects_v2(Bucket=bucket_name, Delimiter='/')
        
        # Get all prefixes (folders)
        for prefix in result.get('CommonPrefixes', []):
            user_id = prefix.get('Prefix', '').rstrip('/')
            if user_id and not user_id.startswith('system/'):
                users.add(user_id)
        
        logger.info(f"Starting metadata cache creation for {len(users)} users")
        
        # For each user, collect video metadata
        for user_id in users:
            try:
                # Check if this is a user folder (starts with @)
                if not user_id.startswith('@'):
                    continue
                
                # Look for metadata JSON files
                metadata_prefix = f"{user_id}/metadata/"
                metadata_objects = []
                
                # List objects with the metadata prefix
                paginator = client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=bucket_name, Prefix=metadata_prefix)
                for page in pages:
                    if 'Contents' in page:
                        metadata_objects.extend(page['Contents'])
                
                # Check if there are any metadata files
                if not metadata_objects:
                    logger.info(f"No metadata found for user {user_id}")
                    continue
                
                user_profile = None
                # Try to get user profile once
                user_meta_key = f"{user_id}/bio/user_meta.json"
                try:
                    response = client.get_object(Bucket=bucket_name, Key=user_meta_key)
                    user_profile = json.loads(response['Body'].read().decode('utf-8'))
                except Exception as e:
                    logger.error(f"Invalid JSON in user profile for {user_id}: {e}")
                    user_profile = None
                
                # Process all video metadata files for the user
                for obj in metadata_objects:
                    if obj['Key'].endswith('.json'):
                        try:
                            response = client.get_object(Bucket=bucket_name, Key=obj['Key'])
                            metadata = json.loads(response['Body'].read().decode('utf-8'))
                            
                            # Enrich metadata with user information
                            metadata['user_id'] = user_id
                            if user_profile:
                                metadata['display_name'] = user_profile.get('display_name', user_id.replace('@', ''))
                            else:
                                metadata['display_name'] = user_id.replace('@', '')
                                
                            # Save thumbnail path but don't generate URL
                            if 'thumbnail_path' in metadata:
                                metadata['has_thumbnail'] = True
                            else:
                                metadata['has_thumbnail'] = False
                                
                            # Format metadata for display
                            views = metadata.get('views', 0)
                            if isinstance(views, (int, str)) and str(views).isdigit():
                                views = int(views)
                                metadata['views_formatted'] = f"{views // 1000}K просмотров" if views >= 1000 else f"{views} просмотров"
                            else:
                                metadata['views_formatted'] = "0 просмотров"
                                
                            upload_date = metadata.get('upload_date', '')
                            if upload_date:
                                try:
                                    from datetime import datetime
                                    upload_datetime = datetime.fromisoformat(upload_date)
                                    metadata['upload_date_formatted'] = upload_datetime.strftime("%d.%m.%Y")
                                except Exception:
                                    metadata['upload_date_formatted'] = upload_date[:10] if upload_date else "Недавно"
                            
                            all_metadata.append(metadata)
                        except Exception as e:
                            logger.error(f"Error processing metadata {obj['Key']}: {e}")
            except Exception as e:
                logger.error(f"Error processing user {user_id}: {e}")
        
        # If no videos found, create empty cache
        if not all_metadata:
            logger.warning("No videos found in the system")
            client.put_object(
                Bucket=bucket_name,
                Key='system/cache/videos_metadata_cache.json',
                Body=json.dumps([]),
                ContentType='application/json'
            )
            return True
        
        # Sort by upload date (newest first)
        all_metadata.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
        
        # Save cache in storage
        client.put_object(
            Bucket=bucket_name,
            Key='system/cache/videos_metadata_cache.json',
            Body=json.dumps(all_metadata),
            ContentType='application/json'
        )
        
        logger.info(f"Successfully cached metadata for {len(all_metadata)} videos")
        return True
    except Exception as e:
        logger.error(f"Error caching metadata: {e}")
        return False

def get_cached_metadata(limit=None, offset=0, shuffle=False):
    """
    Get cached video metadata with pagination.
    
    Args:
        limit: Maximum number of records (if None, returns all)
        offset: Offset for pagination
        shuffle: Whether to shuffle the results
        
    Returns:
        List of video metadata and total number of videos
    """
    try:
        bucket = get_bucket()
        if not bucket:
            logger.error("Could not get bucket for getting cached metadata")
            return [], 0
            
        client = bucket['client']
        bucket_name = bucket['name']
        
        cache_key = 'system/cache/videos_metadata_cache.json'
        
        # Check if cache exists
        try:
            client.head_object(Bucket=bucket_name, Key=cache_key)
        except Exception:
            # If cache doesn't exist, create it
            logger.info("Cache doesn't exist, creating it now")
            cache_video_metadata()
            
            # Check again
            try:
                client.head_object(Bucket=bucket_name, Key=cache_key)
            except Exception:
                logger.error("Failed to create cache")
                return [], 0
        
        # Get cache age
        import time
        from datetime import datetime, timedelta
        
        response = client.head_object(Bucket=bucket_name, Key=cache_key)
        cache_last_modified = response.get('LastModified')
        
        if cache_last_modified:
            cache_age = datetime.now(cache_last_modified.tzinfo) - cache_last_modified
            
            # If cache is older than 15 minutes, update it in background
            if cache_age > timedelta(minutes=0.5):
                logger.info(f"Cache is {cache_age} old, scheduling update")
                # In a real system, you could start a background task here
                # But for simplicity, we'll just update it on the next request
        
        # Load cache
        response = client.get_object(Bucket=bucket_name, Key=cache_key)
        cache_content = response['Body'].read().decode('utf-8')
        all_metadata = json.loads(cache_content)
        
        total_videos = len(all_metadata)
        
        # Shuffle if required
        if shuffle:
            import random
            random.shuffle(all_metadata)
        
        # Check offset validity
        if offset < 0:
            offset = 0
        
        # Apply pagination
        if limit is None:
            paginated_metadata = all_metadata[offset:]
        else:
            try:
                # Convert limit to integer if possible
                limit_int = int(limit)
                paginated_metadata = all_metadata[offset:offset + limit_int]
            except (ValueError, TypeError):
                # In case of error, use offset without limit
                logger.warning(f"Invalid limit value: {limit}, using all items from offset")
                paginated_metadata = all_metadata[offset:]
        
        return paginated_metadata, total_videos
    except Exception as e:
        logger.error(f"Error getting cached metadata: {e}")
        return [], 0

def get_video_url_with_quality(user_id, video_id, quality=None, expiration_time=3600):
    """
    Generate a temporary URL for a video with specified quality
    
    Args:
        user_id (str): User ID (including @ prefix)
        video_id (str): Video ID
        quality (str, optional): Video quality (e.g., '480p', '720p', '1080p')
                                 If None, return highest available quality
        expiration_time (int): URL expiration time in seconds
    
    Returns:
        dict: Information about the URL and available qualities
    """
    metadata = get_video_metadata(user_id, video_id)
    
    if not metadata:
        logger.error(f"Could not find video metadata for {video_id}")
        return None
    
    # Check if video has quality variants
    quality_variants = metadata.get('quality_variants', {})
    available_qualities = metadata.get('available_qualities', [])
    
    # If no quality variants, return the original URL
    if not quality_variants:
        original_url = generate_video_url(user_id, video_id, expiration_time=expiration_time)
        return {
            'url': original_url,
            'quality': 'original',
            'available_qualities': ['original']
        }
    
    # If no quality specified or requested quality not available, use highest available
    if not quality or quality not in available_qualities:
        # Use the highest quality as default (or what's set in metadata)
        quality = metadata.get('highest_quality', available_qualities[-1] if available_qualities else 'original')
    
    # If quality is "original" or not found in variants, return original video
    if quality == 'original' or quality not in quality_variants:
        original_url = generate_video_url(user_id, video_id, expiration_time=expiration_time)
        return {
            'url': original_url,
            'quality': 'original',
            'available_qualities': ['original'] + available_qualities
        }
    
    # Get path for selected quality
    quality_path = quality_variants.get(quality, {}).get('path')
    
    # If path not found, return original video
    if not quality_path:
        original_url = generate_video_url(user_id, video_id, expiration_time=expiration_time)
        return {
            'url': original_url,
            'quality': 'original',
            'available_qualities': ['original'] + available_qualities
        }
    
    # Generate signed URL for selected quality
    bucket = get_bucket()
    if not bucket:
        logger.error(f"Could not get bucket for generating URL")
        return None
    
    client = bucket['client']
    bucket_name = bucket['name']
    
    # Check if quality variant exists
    try:
        client.head_object(Bucket=bucket_name, Key=quality_path)
    except Exception:
        logger.error(f"Quality variant {quality} not found for video {video_id}")
        # Fallback to original
        original_url = generate_video_url(user_id, video_id, expiration_time=expiration_time)
        return {
            'url': original_url,
            'quality': 'original',
            'available_qualities': ['original'] + available_qualities
        }
    
    try:
        url = client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': quality_path
            },
            ExpiresIn=expiration_time
        )
        
        logger.info(f"Generated URL for video {video_id} at quality {quality}")
        
        # Return URL and available qualities
        return {
            'url': url,
            'quality': quality,
            'available_qualities': available_qualities
        }
    
    except Exception as e:
        logger.error(f"Error generating URL for quality variant: {e}")
        # Fallback to original
        original_url = generate_video_url(user_id, video_id, expiration_time=expiration_time)
        return {
            'url': original_url,
            'quality': 'original',
            'available_qualities': ['original'] + available_qualities
        }

def upload_video_with_quality_processing(user_id, video_file_path, title=None, description=None, process_qualities=True):
    """
    Upload video to storage and create quality variants
    
    Args:
        user_id (str): User ID (with @ prefix)
        video_file_path (str): Path to the video file
        title (str, optional): Video title
        description (str, optional): Video description
        process_qualities (bool): Whether to process different quality variants
    
    Returns:
        str: Video ID if successful, None otherwise
    """
    # First upload the original video
    video_id = upload_video(user_id, video_file_path, title, description)
    
    if not video_id:
        logger.error(f"Failed to upload original video, canceling quality processing")
        return video_id
    
    # Now process different quality variants if requested
    if process_qualities:
        try:
            # Determine which module to import based on which one exists
            try:
                from .video_quality_s3 import create_quality_variants
                logger.info("Using S3-specific video quality processing")
            except ImportError:
                try:
                    from .video_quality import create_quality_variants
                    logger.info("Using general video quality processing")
                except ImportError:
                    logger.error("Could not import video quality processing module")
                    return video_id
            
            logger.info(f"Starting quality variant creation for video {video_id}")
            
            # Create quality variants synchronously
            quality_variants = create_quality_variants(video_file_path, user_id, video_id)
            
            if quality_variants:
                logger.info(f"Successfully created {len(quality_variants)} quality variants for video {video_id}")
            else:
                logger.warning(f"No quality variants created for video {video_id}")
        
        except Exception as e:
            logger.error(f"Error processing quality variants: {str(e)}")
            # Continue since the original video was uploaded successfully
    else:
        logger.info(f"Quality processing skipped for video {video_id} as requested")
    
    return video_id