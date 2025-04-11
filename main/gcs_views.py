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

logger = logging.getLogger(__name__)

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
    Handler for uploading video to Google Cloud Storage with improved error handling
    """
    try:
        # Get files and data from request
        video_file = request.FILES.get('video_file')
        thumbnail = request.FILES.get('thumbnail')
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        category_id = request.POST.get('category')
        
        if not video_file or not title:
            return JsonResponse({'error': 'Video and title are required'}, status=400)
        
        # Create temp directory if it doesn't exist
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Get cleaned username for GCS storage
        username = request.user.username
        if username.startswith('@'):
            username = username[1:]
        
        # Save files temporarily on server
        temp_video_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{video_file.name}")
        
        with open(temp_video_path, 'wb+') as destination:
            for chunk in video_file.chunks():
                destination.write(chunk)
        
        # Upload video to GCS
        video_id = upload_video(
            user_id=username,
            video_file_path=temp_video_path,
            title=title,
            description=description
        )
        
        # If video upload failed
        if not video_id:
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            return JsonResponse({'error': 'Failed to upload video to Google Cloud Storage'}, status=500)
        
        # If thumbnail exists, upload it too
        thumbnail_url = None
        if thumbnail:
            temp_thumbnail_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{thumbnail.name}")
            with open(temp_thumbnail_path, 'wb+') as destination:
                for chunk in thumbnail.chunks():
                    destination.write(chunk)
            
            thumbnail_success = upload_thumbnail(username, video_id, temp_thumbnail_path)
            
            # Remove temporary thumbnail file
            if os.path.exists(temp_thumbnail_path):
                os.remove(temp_thumbnail_path)
                
            if thumbnail_success:
                # Get thumbnail URL
                metadata = get_video_metadata(username, video_id)
                if metadata and "thumbnail_path" in metadata:
                    thumbnail_url = generate_video_url(
                        username, 
                        video_id, 
                        file_path=metadata["thumbnail_path"], 
                        expiration_time=3600
                    )
        
        # Remove temporary video file
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        
        # Get metadata for uploaded video
        video_metadata = get_video_metadata(username, video_id)
        
        # Generate temporary URL for video access
        video_url = generate_video_url(username, video_id, expiration_time=3600)
        
        # Add URLs to metadata
        if video_metadata:
            video_metadata['url'] = video_url
            if thumbnail_url:
                video_metadata['thumbnail_url'] = thumbnail_url
                
            # Create or update Video object in database if needed
            try:
                # If category is used
                category = None
                if category_id:
                    try:
                        category = Category.objects.get(id=category_id)
                    except Category.DoesNotExist:
                        pass
                
                # Check if video already exists
                video_obj, created = Video.objects.get_or_create(
                    title=title,
                    defaults={
                        'channel_id': 1,  # Assume channel is already created
                        'category': category,
                        'views': '0',
                        'age_text': 'Just now',
                        'duration': video_metadata.get('duration', '00:00'),
                    }
                )
                
                video_metadata['video_db_id'] = video_obj.id
            except Exception as db_err:
                logger.error(f"Error creating database record: {db_err}")
                # Don't return error since video is already uploaded to GCS
        
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
    Get user's video list from GCS with improved handling
    """
    try:
        username = request.user.username
        if username.startswith('@'):
            username = username[1:]
            
        videos = list_user_videos(username)
        
        # Add temporary URLs to each video
        for video in videos:
            video_id = video.get('video_id')
            if video_id:
                # URL for video
                video['url'] = generate_video_url(username, video_id, expiration_time=3600)
                
                # URL for thumbnail if it exists
                if 'thumbnail_path' in video:
                    video['thumbnail_url'] = generate_video_url(
                        username, 
                        video_id, 
                        file_path=video['thumbnail_path'], 
                        expiration_time=3600
                    )
        
        return JsonResponse({
            'success': True,
            'videos': videos
        })
        
    except Exception as e:
        logger.error(f"Error getting video list: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

# Improved function for URL generation
def generate_video_url(user_id, video_id, file_path=None, expiration_time=3600):
    """
    Enhanced version for generating temporary URLs
    """
    from .gcs_storage import get_bucket, get_video_metadata
    
    try:
        bucket = get_bucket()
        if not bucket:
            logger.error("Failed to get bucket")
            return None
            
        # If specific file path provided (e.g., for thumbnail)
        if file_path:
            blob = bucket.blob(file_path)
            if not blob.exists():
                logger.error(f"File not found at path: {file_path}")
                return None
        else:
            # Get video file path from metadata
            metadata = get_video_metadata(user_id, video_id)
            if not metadata or "file_path" not in metadata:
                logger.error(f"Could not find information about video {video_id}")
                return None
            
            blob = bucket.blob(metadata["file_path"])
            if not blob.exists():
                logger.error(f"Video file not found in storage")
                return None
        
        # Generate URL
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
    View for the studio page with GCS integration
    """
    # Check if user is an author
    if not request.user.profile.is_author:
        messages.error(request, 'You don\'t have access to Studio. You need to become an author to gain access.')
        return redirect('become_author')
    
    # Get user's videos from GCS
    username = request.user.username
    if username.startswith('@'):
        username = username[1:]
    
    try:
        # Get user's videos
        videos = list_user_videos(username)
        
        # Get categories for upload form
        categories = Category.objects.all()
        
        return render(request, 'studio/studio.html', {
            'videos': videos,
            'categories': categories
        })
    except Exception as e:
        messages.error(request, f'Error retrieving data: {e}')
        
    return render(request, 'studio/studio.html', {
        'videos': []
    })
    
@login_required
@require_http_methods(["DELETE"])
def delete_video_from_gcs(request, video_id):
    """
    Delete video from GCS
    """
    try:
        username = request.user.username
        if username.startswith('@'):
            username = username[1:]
            
        success = delete_video(username, video_id)
        
        if success:
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'error': 'Failed to delete video'}, status=400)
            
    except Exception as e:
        logger.error(f"Error deleting video: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["GET"])
def get_video_url(request, video_id):
    """
    Get temporary URL for video
    """
    try:
        username = request.user.username
        if username.startswith('@'):
            username = username[1:]
            
        url = generate_video_url(username, video_id, expiration_time=3600)
        
        if url:
            return JsonResponse({
                'success': True,
                'url': url
            })
        else:
            return JsonResponse({'error': 'Failed to generate URL'}, status=400)
            
    except Exception as e:
        logger.error(f"Error generating URL: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)