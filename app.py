from flask import Flask, render_template, jsonify, request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import os
import json
import isodate
from config import config

app = Flask(__name__)
app.config.from_object(config[os.environ.get('FLASK_ENV', 'development')])

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube"  # Required for Groups management
]

def authenticate():
    """Authenticate with Google OAuth (development only)."""
    if os.environ.get('FLASK_ENV') == 'production':
        print("OAuth flow not available in production")
        return None
    
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=8080, access_type='offline', prompt='consent')
    return creds

def get_credentials():
    """Get valid user credentials from storage or environment variables with robust error handling."""
    creds = None
    
    # Check if we have credentials in environment variables (production)
    if os.environ.get('GOOGLE_CREDENTIALS'):
        try:
            creds_data = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
            print("✅ Loaded credentials from environment variables")
        except Exception as e:
            print(f"❌ Error loading credentials from environment: {e}")
            return None
    
    # Fallback to local files (development)
    if not creds and os.path.exists("token.json"):
        try:
            with open("token.json", "r") as token_file:
                creds_data = json.load(token_file)
            
            # Validate that the token has required fields
            if 'refresh_token' not in creds_data:
                print("❌ Token file missing refresh_token - will re-authenticate")
                os.remove("token.json")
                return None
                
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
            print("✅ Loaded credentials from token.json")
        except Exception as e:
            print(f"❌ Error loading credentials from file: {e}")
            # Delete corrupted token file and start fresh
            try:
                os.remove("token.json")
                print("🗑️ Deleted corrupted token.json file")
            except:
                pass
            return None
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("🔄 Refreshing expired credentials...")
                creds.refresh(Request())
                print("✅ Successfully refreshed credentials")
                
                # Save refreshed credentials
                if os.environ.get('FLASK_ENV') != 'production':
                    with open("token.json", "w") as token:
                        token.write(creds.to_json())
                    print("💾 Saved refreshed credentials to token.json")
                    
            except Exception as e:
                print(f"❌ Error refreshing credentials: {e}")
                # Delete the corrupted token and start fresh
                try:
                    os.remove("token.json")
                    print("🗑️ Deleted corrupted token.json after refresh failure")
                except:
                    pass
                return None
        else:
            # For production, we need to handle OAuth flow differently
            if os.environ.get('FLASK_ENV') == 'production':
                print("❌ Production environment requires valid credentials")
                return None
            else:
                # Development OAuth flow
                print("🔐 Starting OAuth flow for new authentication...")
                try:
                    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
                    creds = flow.run_local_server(port=8080, access_type='offline', prompt='consent')
                    print("✅ OAuth authentication successful")
                    
                    # Save the credentials for the next run (development only)
                    with open("token.json", "w") as token:
                        token.write(creds.to_json())
                    print("💾 Saved new credentials to token.json")
                    
                except Exception as e:
                    print(f"❌ OAuth authentication failed: {e}")
                    return None
    
    # Final validation
    if not creds or not creds.valid:
        print("❌ Final credential validation failed")
        return None
    
    print("✅ Credentials are valid and ready to use")
    return creds

def get_cache_key():
    """Generate a cache key for current 6-hour period"""
    now = datetime.now()
    # 6-hour periods: 00-05, 06-11, 12-17, 18-23
    period = now.hour // 6
    period_names = ["night", "morning", "afternoon", "evening"]
    date = now.strftime("%Y-%m-%d")
    return f"videos_cache_{date}_{period_names[period]}.json"

def is_cache_valid(cache_file, max_age_hours=6):
    """Check if cache file is still valid (default 6 hours)"""
    if not os.path.exists(cache_file):
        return False
    
    # Check if file is within the max age
    file_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
    now = datetime.now()
    age_hours = (now - file_time).total_seconds() / 3600
    
    return age_hours < max_age_hours

def load_from_cache(cache_file):
    """Load data from cache file"""
    try:
        with open(cache_file, 'r') as f:
            return json.load(f)
    except:
        return None

def save_to_cache(cache_file, data):
    """Save data to cache file"""
    try:
        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Saved cache: {cache_file}")
    except Exception as e:
        print(f"Error saving cache: {e}")

def clear_old_cache():
    """Remove cache files older than 24 hours"""
    cache_dir = "."
    
    for file in os.listdir(cache_dir):
        if file.startswith("videos_cache_") and file.endswith(".json"):
            file_path = os.path.join(cache_dir, file)
            
            if not is_cache_valid(file_path, max_age_hours=24):
                try:
                    os.remove(file_path)
                    print(f"Removed old cache: {file}")
                except:
                    pass



def get_video_metrics(video_id, youtube_analytics, youtube_data):
    """Get metrics for a single video (fallback for small batches)"""
    try:
        # Get video duration using Data API
        video_req = youtube_data.videos().list(
            part="snippet,contentDetails,statistics,status",
            id=video_id
        )
        video_res = video_req.execute()
        if not video_res.get("items"):
            return None
        video_item = video_res["items"][0]

        duration_iso = video_item["contentDetails"]["duration"]
        duration_sec = isodate.parse_duration(duration_iso).total_seconds()
        
        # Format duration as MM:SS or M:SS
        minutes = int(duration_sec // 60)
        seconds = int(duration_sec % 60)
        video_length = f"{minutes}:{seconds:02d}"

        published_at = video_item["snippet"]["publishedAt"]
        published_date = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")

        # Get channel ID from the video's channel
        channel_id = video_item["snippet"]["channelId"]

        # Get analytics data
        today = datetime.today().strftime('%Y-%m-%d')
        
        analytics_req = youtube_analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate="2024-01-01",
            endDate=today,
            metrics="views,likes,averageViewDuration,averageViewPercentage,subscribersGained",
            dimensions="video",
            filters=f"video=={video_id}"
        )
        analytics_res = analytics_req.execute()

        rows = analytics_res.get("rows", [])
        if not rows:
            # Fallback to basic stats from Data API
            stats = video_item.get("statistics", {})
            return {
                "published": published_date,
                "video_length": video_length,
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "avg_duration": 0,
                "avg_view_percent": 0,
                "subs_gained": 0,
                "title": video_item["snippet"]["title"],
                "thumbnail": video_item["snippet"]["thumbnails"]["medium"]["url"],
                "status": video_item.get("status", {}).get("privacyStatus", "unknown")
            }
        
        row = rows[0]
        return {
            "published": published_date,
            "video_length": video_length,
            "views": int(row[1]),
            "likes": int(row[2]),
            "avg_duration": float(row[3]),
            "avg_view_percent": float(row[4]),
            "subs_gained": int(row[5]),
            "title": video_item["snippet"]["title"],
            "thumbnail": video_item["snippet"]["thumbnails"]["medium"]["url"],
            "status": video_item.get("status", {}).get("privacyStatus", "unknown")
        }
    except Exception as e:
        print(f"Error getting metrics for {video_id}: {e}")
        return None

def get_or_create_video_group(youtube_analytics, video_ids):
    """Get existing group or create new one with current videos"""
    try:
        # Check if we have an existing group
        existing_groups = youtube_analytics.groups().list().execute()
        
        if existing_groups.get("items"):
            group = existing_groups["items"][0]  # Use first group
            print(f"Using existing group: {group['snippet']['title']}")
            
            # Update group with current video list
            update_group_items(group["id"], video_ids, youtube_analytics)
            
            return group["id"]
        else:
            # Create new group
            print("Creating new video analytics group...")
            return create_new_group(video_ids, youtube_analytics)
            
    except Exception as e:
        print(f"Error managing video group: {e}")
        return None

def create_new_group(video_ids, youtube_analytics):
    """Create a new group and add videos to it"""
    try:
        # Create the group
        group = youtube_analytics.groups().insert(
            body={
                "snippet": {
                    "title": "YT Dashboard Videos"
                },
                "contentDetails": {
                    "itemType": "youtube#video"
                }
            }
        ).execute()
        
        group_id = group["id"]
        print(f"Created new group: {group_id}")
        
        # Add videos to the group
        add_videos_to_group(group_id, video_ids, youtube_analytics)
        
        return group_id
        
    except Exception as e:
        print(f"Error creating group: {e}")
        return None

def update_group_items(group_id, current_video_ids, youtube_analytics):
    """Update group to match current video list"""
    try:
        # Get current items in group
        current_items = youtube_analytics.groupItems().list(
            groupId=group_id
        ).execute()
        
        current_group_videos = set()
        if current_items.get("items"):
            current_group_videos = {item["resource"]["id"] for item in current_items["items"]}
        
        current_video_set = set(current_video_ids)
        
        # Find videos to add and remove
        videos_to_add = current_video_set - current_group_videos
        videos_to_remove = current_group_videos - current_video_set
        
        # Remove videos that are no longer needed
        for video_id in videos_to_remove:
            try:
                youtube_analytics.groupItems().delete(
                    groupId=group_id,
                    id=video_id
                ).execute()
                print(f"Removed video {video_id} from group")
            except Exception as e:
                print(f"Error removing video {video_id}: {e}")
        
        # Add new videos
        add_videos_to_group(group_id, list(videos_to_add), youtube_analytics)
        
        if videos_to_add or videos_to_remove:
            print(f"Updated group: +{len(videos_to_add)} videos, -{len(videos_to_remove)} videos")
        else:
            print("Group is up to date")
            
    except Exception as e:
        print(f"Error updating group items: {e}")

def add_videos_to_group(group_id, video_ids, youtube_analytics):
    """Add videos to an existing group"""
    if not video_ids:
        return
        
    for video_id in video_ids:
        try:
            youtube_analytics.groupItems().insert(
                groupId=group_id,
                body={
                    "resource": {
                        "id": video_id,
                        "kind": "youtube#video"
                    }
                }
            ).execute()
            print(f"Added video {video_id} to group")
        except Exception as e:
            print(f"Error adding video {video_id} to group: {e}")

def get_group_analytics(group_id, youtube_analytics, youtube_data):
    """Get analytics data for all videos in a group"""
    try:
        today = datetime.today().strftime('%Y-%m-%d')
        
        # Query analytics for the entire group
        analytics_req = youtube_analytics.reports().query(
            ids=f"group=={group_id}",
            startDate="2024-01-01",
            endDate=today,
            metrics="views,likes,averageViewDuration,averageViewPercentage,subscribersGained",
            dimensions="video"
        )
        analytics_res = analytics_req.execute()
        
        # Create a map of video_id to analytics data
        analytics_map = {}
        for row in analytics_res.get("rows", []):
            video_id = row[0]
            analytics_map[video_id] = {
                "views": int(row[1]),
                "likes": int(row[2]),
                "avg_duration": float(row[3]),
                "avg_view_percent": float(row[4]),
                "subs_gained": int(row[5])
            }
        
        # Get video details from Data API
        video_ids = list(analytics_map.keys())
        if not video_ids:
            return []
            
        video_ids_str = ','.join(video_ids)
        video_req = youtube_data.videos().list(
            part="snippet,contentDetails,statistics,status",
            id=video_ids_str
        )
        video_res = video_req.execute()
        video_items = video_res.get("items", [])
        
        # Combine analytics and video data
        results = []
        for video_item in video_items:
            video_id = video_item["id"]
            analytics = analytics_map.get(video_id)
            
            if not analytics:
                continue
                
            # Format duration
            duration_iso = video_item["contentDetails"]["duration"]
            duration_sec = isodate.parse_duration(duration_iso).total_seconds()
            minutes = int(duration_sec // 60)
            seconds = int(duration_sec % 60)
            video_length = f"{minutes}:{seconds:02d}"
            
            # Format published date
            published_at = video_item["snippet"]["publishedAt"]
            published_date = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")
            
            result = {
                "published": published_date,
                "video_length": video_length,
                "views": analytics["views"],
                "likes": analytics["likes"],
                "avg_duration": analytics["avg_duration"],
                "avg_view_percent": analytics["avg_view_percent"],
                "subs_gained": analytics["subs_gained"],
                "title": video_item["snippet"]["title"],
                "thumbnail": video_item["snippet"]["thumbnails"]["medium"]["url"],
                "status": video_item.get("status", {}).get("privacyStatus", "unknown")
            }
            
            results.append(result)
        
        return results
        
    except Exception as e:
        print(f"Error getting group analytics: {e}")
        return []

@app.route('/')
def dashboard():
    return app.send_static_file('dashboard.html')

@app.route('/api/videos')
def get_videos():
    try:
        # Get credentials first with better error handling
        try:
            creds = get_credentials()
            if not creds:
                print("❌ No credentials available - authentication required")
                return jsonify({"error": "Authentication required. Please check your credentials."}), 401
        except Exception as auth_error:
            print(f"❌ Authentication error: {auth_error}")
            return jsonify({"error": f"Authentication failed: {str(auth_error)}"}), 401
        
        # Get query parameters for pagination and sorting
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 5))
        sort_by = request.args.get('sort_by', 'published')
        sort_direction = request.args.get('sort_direction', 'desc')
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        # Clear cache if force refresh is requested
        if force_refresh:
            print("🔄 Force refresh requested - clearing cache...")
            clear_old_cache()
        
        # Check cache first (unless force refresh is requested)
        cache_file = get_cache_key()
        if not force_refresh and is_cache_valid(cache_file):
            cached_data = load_from_cache(cache_file)
            if cached_data:
                # Sort cached data
                all_videos = cached_data.get("videos", [])
                reverse_sort = sort_direction == 'desc'
                
                if sort_by == 'title':
                    all_videos.sort(key=lambda x: x['title'].lower(), reverse=reverse_sort)
                elif sort_by == 'published':
                    all_videos.sort(key=lambda x: x['published'], reverse=reverse_sort)
                elif sort_by == 'views':
                    all_videos.sort(key=lambda x: x['views'], reverse=reverse_sort)
                elif sort_by == 'likes':
                    all_videos.sort(key=lambda x: x['likes'], reverse=reverse_sort)
                elif sort_by == 'length':
                    all_videos.sort(key=lambda x: sum(int(t) * 60 ** i for i, t in enumerate(reversed(x['video_length'].split(':')))), reverse=reverse_sort)
                elif sort_by == 'watchTime':
                    all_videos.sort(key=lambda x: x['avg_duration'], reverse=reverse_sort)
                elif sort_by == 'watched':
                    all_videos.sort(key=lambda x: x['avg_view_percent'], reverse=reverse_sort)
                elif sort_by == 'subs':
                    all_videos.sort(key=lambda x: x['subs_gained'], reverse=reverse_sort)
                
                return jsonify({
                    "videos": all_videos,
                    "last_updated": cached_data.get("last_updated"),
                    "cached": True,
                    "total_videos_fetched": cached_data.get("total_videos_fetched", len(all_videos)),
                    "total_videos_available": cached_data.get("total_videos_available", len(all_videos))
                })
        
        # If no cache, fetch from YouTube APIs
        print("Fetching fresh data from YouTube APIs...")
        try:
            youtube = build("youtube", "v3", credentials=creds)
            youtube_analytics = build("youtubeAnalytics", "v2", credentials=creds)
        except Exception as build_error:
            print(f"❌ Failed to build YouTube API clients: {build_error}")
            return jsonify({"error": f"Failed to initialize YouTube APIs: {str(build_error)}"}), 500

        # Get all video IDs (up to 50 videos)
        try:
            search_request = youtube.search().list(
                part="snippet",
                forMine=True,
                type="video",
                maxResults=50,  # Get up to 50 videos
                order="date"
            )
            response = search_request.execute()
        except Exception as search_error:
            print(f"❌ Failed to search for videos: {search_error}")
            return jsonify({"error": f"Failed to search for videos: {str(search_error)}"}), 500
        
        # Get all video IDs
        all_video_items = response.get("items", [])
        video_ids = [item["id"]["videoId"] for item in all_video_items]
        total_videos_fetched = len(video_ids)
        
        # Get total count for display purposes
        try:
            total_search_request = youtube.search().list(
                part="snippet",
                forMine=True,
                type="video",
                maxResults=1,  # Just get count
                order="date"
            )
            total_response = total_search_request.execute()
            total_videos_available = total_response.get("pageInfo", {}).get("totalResults", 0)
        except Exception as total_error:
            print(f"❌ Failed to get total video count: {total_error}")
            total_videos_available = total_videos_fetched  # Fallback to fetched count
        
        print(f"Fetching metrics for {total_videos_fetched} videos")
        
        # Use individual calls with retry logic for network reliability
        all_metrics = []
        successful_calls = 0
        
        for i, video_id in enumerate(video_ids, 1):
            print(f"Processing video {i}/{total_videos_fetched}: {video_id}")
            
            # Retry up to 3 times for each video
            for attempt in range(3):
                try:
                    metrics = get_video_metrics(video_id, youtube_analytics, youtube)
                    if metrics:
                        all_metrics.append(metrics)
                        successful_calls += 1
                        print(f"  ✅ Success (attempt {attempt + 1})")
                        break
                    else:
                        print(f"  ⚠️  No data for video {video_id}")
                        break
                except Exception as e:
                    if attempt < 2:  # Not the last attempt
                        print(f"  🔄 Retry {attempt + 1}/3: {e}")
                        import time
                        time.sleep(1)  # Wait 1 second before retry
                    else:
                        print(f"  ❌ Failed after 3 attempts: {e}")
        
        print(f"✅ Successfully processed {successful_calls}/{total_videos_fetched} videos")
        all_videos = [metrics for metrics in all_metrics if metrics and metrics.get("status") == "public"]

        # Sort all videos on server side
        reverse_sort = sort_direction == 'desc'
        
        if sort_by == 'title':
            all_videos.sort(key=lambda x: x['title'].lower(), reverse=reverse_sort)
        elif sort_by == 'published':
            all_videos.sort(key=lambda x: x['published'], reverse=reverse_sort)
        elif sort_by == 'views':
            all_videos.sort(key=lambda x: x['views'], reverse=reverse_sort)
        elif sort_by == 'likes':
            all_videos.sort(key=lambda x: x['likes'], reverse=reverse_sort)
        elif sort_by == 'length':
            all_videos.sort(key=lambda x: sum(int(t) * 60 ** i for i, t in enumerate(reversed(x['video_length'].split(':')))), reverse=reverse_sort)
        elif sort_by == 'watchTime':
            all_videos.sort(key=lambda x: x['avg_duration'], reverse=reverse_sort)
        elif sort_by == 'watched':
            all_videos.sort(key=lambda x: x['avg_view_percent'], reverse=reverse_sort)
        elif sort_by == 'subs':
            all_videos.sort(key=lambda x: x['subs_gained'], reverse=reverse_sort)

        # No pagination - return all videos

        # Add dashboard-level last updated timestamp (yesterday's date)
        yesterday = datetime.now() - timedelta(days=1)
        
        # Cache all videos
        dashboard_data = {
            "videos": all_videos,  # Store all videos in cache
            "last_updated": yesterday.strftime("%Y-%m-%d"),
            "total_videos_fetched": total_videos_fetched,
            "total_videos_available": total_videos_available
        }

        # Save to cache
        save_to_cache(cache_file, dashboard_data)
        
        # Clear old cache files
        clear_old_cache()

        return jsonify({
            "videos": all_videos,
            "last_updated": yesterday.strftime("%Y-%m-%d"),
            "total_videos_fetched": total_videos_fetched,
            "total_videos_available": total_videos_available
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/clear-cache')
def clear_cache():
    """Clear all cache files"""
    try:
        clear_old_cache()
        return jsonify({"message": "Cache cleared successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/channel')
def get_channel():
    try:
        # Get credentials first
        creds = get_credentials()
        if not creds:
            return jsonify({
                "title": "YouTube Dashboard",
                "description": "Sign in to view your channel",
                "thumbnail": "",
                "subscriberCount": 0,
                "videoCount": 0,
                "viewCount": 0,
                "error": "Authentication required"
            }), 401
        
        youtube = build("youtube", "v3", credentials=creds)
        
        channel_request = youtube.channels().list(
            part="snippet,statistics",
            mine=True
        )
        response = channel_request.execute()
        
        if response.get("items"):
            channel = response["items"][0]
            return jsonify({
                "title": channel["snippet"]["title"],
                "description": channel["snippet"]["description"],
                "thumbnail": channel["snippet"]["thumbnails"]["default"]["url"],
                "subscriberCount": channel["statistics"].get("subscriberCount", 0),
                "videoCount": channel["statistics"].get("videoCount", 0),
                "viewCount": channel["statistics"].get("viewCount", 0)
            })
        
        # Fallback if no channel found
        return jsonify({
            "title": "YouTube Dashboard",
            "description": "No channel found",
            "thumbnail": "",
            "subscriberCount": 0,
            "videoCount": 0,
            "viewCount": 0,
            "error": "No channel found"
        }), 404
        
    except Exception as e:
        print(f"Channel API error: {e}")
        # Fallback on any error
        return jsonify({
            "title": "YouTube Dashboard",
            "description": "Error loading channel",
            "thumbnail": "",
            "subscriberCount": 0,
            "videoCount": 0,
            "viewCount": 0,
            "error": "Channel loading failed"
        }), 500

# Global error handler for unhandled exceptions
@app.errorhandler(Exception)
def handle_exception(e):
    """Handle any unhandled exceptions"""
    print(f"❌ Unhandled exception: {e}")
    print(f"❌ Exception type: {type(e).__name__}")
    import traceback
    print(f"❌ Traceback: {traceback.format_exc()}")
    return jsonify({"error": "Internal server error occurred"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000, use_reloader=False) 