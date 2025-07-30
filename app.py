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
    "https://www.googleapis.com/auth/yt-analytics.readonly"
]

def authenticate():
    """Authenticate with Google OAuth (development only)."""
    if os.environ.get('FLASK_ENV') == 'production':
        print("OAuth flow not available in production")
        return None
    
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    creds = flow.run_local_server(port=0)
    return creds

def get_credentials():
    """Get valid user credentials from storage or environment variables."""
    creds = None
    
    # Check if we have credentials in environment variables (production)
    if os.environ.get('GOOGLE_CREDENTIALS'):
        try:
            creds_data = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
        except Exception as e:
            print(f"Error loading credentials from environment: {e}")
            return None
    
    # Fallback to local files (development)
    if not creds and os.path.exists("token.json"):
        try:
            with open("token.json", "r") as token_file:
                creds_data = json.load(token_file)
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
        except Exception as e:
            print(f"Error loading credentials from file: {e}")
            return None
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing credentials: {e}")
                return None
        else:
            # For production, we need to handle OAuth flow differently
            if os.environ.get('FLASK_ENV') == 'production':
                print("Production environment requires valid credentials")
                return None
            else:
                # Development OAuth flow
                flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
                creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run (development only)
        if os.environ.get('FLASK_ENV') != 'production':
            with open("token.json", "w") as token:
                token.write(creds.to_json())
    
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
    """Get metrics for a single video"""
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

        # Get analytics data
        today = datetime.today().strftime('%Y-%m-%d')
        channel_id = "UCtE-eeBIIZHw7qnF7vH-Chg"
        
        analytics_req = youtube_analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate="2025-01-01",
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

@app.route('/')
def dashboard():
    return app.send_static_file('dashboard.html')

@app.route('/api/videos')
def get_videos():
    try:
        # Get credentials first
        creds = get_credentials()
        if not creds:
            return jsonify({"error": "Authentication required. Please check your credentials."}), 401
        
        # Get query parameters for pagination and sorting
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        sort_by = request.args.get('sort_by', 'published')
        sort_direction = request.args.get('sort_direction', 'desc')
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        # Check cache first (unless force refresh is requested)
        cache_file = get_cache_key()
        if not force_refresh and is_cache_valid(cache_file):
            cached_data = load_from_cache(cache_file)
            if cached_data:
                # Sort cached data
                videos = cached_data.get("videos", [])
                reverse_sort = sort_direction == 'desc'
                
                if sort_by == 'title':
                    videos.sort(key=lambda x: x['title'].lower(), reverse=reverse_sort)
                elif sort_by == 'published':
                    videos.sort(key=lambda x: x['published'], reverse=reverse_sort)
                elif sort_by == 'views':
                    videos.sort(key=lambda x: x['views'], reverse=reverse_sort)
                elif sort_by == 'likes':
                    videos.sort(key=lambda x: x['likes'], reverse=reverse_sort)
                elif sort_by == 'length':
                    videos.sort(key=lambda x: sum(int(t) * 60 ** i for i, t in enumerate(reversed(x['video_length'].split(':')))), reverse=reverse_sort)
                elif sort_by == 'watchTime':
                    videos.sort(key=lambda x: x['avg_duration'], reverse=reverse_sort)
                elif sort_by == 'watched':
                    videos.sort(key=lambda x: x['avg_view_percent'], reverse=reverse_sort)
                elif sort_by == 'subs':
                    videos.sort(key=lambda x: x['subs_gained'], reverse=reverse_sort)
                
                # Paginate cached data
                total_videos = len(videos)
                total_pages = (total_videos + per_page - 1) // per_page
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page
                paginated_videos = videos[start_idx:end_idx]
                
                return jsonify({
                    "videos": paginated_videos,
                    "last_updated": cached_data.get("last_updated"),
                    "cached": True,
                    "pagination": {
                        "current_page": page,
                        "per_page": per_page,
                        "total_videos": total_videos,
                        "total_pages": total_pages,
                        "has_next": page < total_pages,
                        "has_prev": page > 1
                    }
                })
        
        # If no cache, fetch from YouTube APIs
        print("Fetching fresh data from YouTube APIs...")
        youtube = build("youtube", "v3", credentials=creds)
        youtube_analytics = build("youtubeAnalytics", "v2", credentials=creds)

        # Get video IDs first
        search_request = youtube.search().list(
            part="snippet",
            forMine=True,
            type="video",
            maxResults=50,  # Get 50 videos total
            order="date"
        )
        response = search_request.execute()

        # Get metrics for each video
        videos = []
        for item in response.get("items", []):
            video_id = item["id"]["videoId"]
            metrics = get_video_metrics(video_id, youtube_analytics, youtube)
            if metrics and metrics.get("status") == "public":
                videos.append(metrics)

        # Sort videos on server side
        reverse_sort = sort_direction == 'desc'
        
        if sort_by == 'title':
            videos.sort(key=lambda x: x['title'].lower(), reverse=reverse_sort)
        elif sort_by == 'published':
            videos.sort(key=lambda x: x['published'], reverse=reverse_sort)
        elif sort_by == 'views':
            videos.sort(key=lambda x: x['views'], reverse=reverse_sort)
        elif sort_by == 'likes':
            videos.sort(key=lambda x: x['likes'], reverse=reverse_sort)
        elif sort_by == 'length':
            videos.sort(key=lambda x: sum(int(t) * 60 ** i for i, t in enumerate(reversed(x['video_length'].split(':')))), reverse=reverse_sort)
        elif sort_by == 'watchTime':
            videos.sort(key=lambda x: x['avg_duration'], reverse=reverse_sort)
        elif sort_by == 'watched':
            videos.sort(key=lambda x: x['avg_view_percent'], reverse=reverse_sort)
        elif sort_by == 'subs':
            videos.sort(key=lambda x: x['subs_gained'], reverse=reverse_sort)

        # Paginate results
        total_videos = len(videos)
        total_pages = (total_videos + per_page - 1) // per_page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_videos = videos[start_idx:end_idx]

        # Add dashboard-level last updated timestamp (yesterday's date)
        yesterday = datetime.now() - timedelta(days=1)
        dashboard_data = {
            "videos": videos,  # Store all videos in cache
            "last_updated": yesterday.strftime("%Y-%m-%d")
        }

        # Save to cache
        save_to_cache(cache_file, dashboard_data)
        
        # Clear old cache files
        clear_old_cache()

        return jsonify({
            "videos": paginated_videos,
            "last_updated": yesterday.strftime("%Y-%m-%d"),
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_videos": total_videos,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/channel')
def get_channel():
    try:
        # Get credentials first
        creds = get_credentials()
        if not creds:
            return jsonify({"error": "Authentication required. Please check your credentials."}), 401
        
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
        return jsonify({"error": "No channel found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000) 