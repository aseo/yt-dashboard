from flask import Flask, render_template, jsonify, request, session, redirect, url_for, flash
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import json
import pickle
import glob
import isodate
from datetime import datetime, timedelta
import config
from config import config

def clear_old_cache_files():
    """Clear all old cache files to prevent structure mismatches"""
    try:
        cache_files = glob.glob("videos_cache_*.json")
        for cache_file in cache_files:
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                
                # Check if cache has the correct structure
                videos = cached_data.get('videos', [])
                if videos and len(videos) > 0:
                    first_video = videos[0]
                    required_fields = ['percentWatched', 'watchTime', 'subsGained', 'publishedAt', 'length']
                    if not all(field in first_video for field in required_fields):
                        print(f"🗑️ Removing old cache file with invalid structure: {cache_file}")
                        os.remove(cache_file)
            except Exception as e:
                print(f"🗑️ Removing corrupted cache file: {cache_file}")
                os.remove(cache_file)
    except Exception as e:
        print(f"❌ Error clearing old cache files: {e}")

# Clear old cache files on app startup
clear_old_cache_files()

app = Flask(__name__)
app.config.from_object(config[os.environ.get('FLASK_ENV', 'development')])

# Enable sessions for user authentication
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Set session to last 24 hours
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
    'https://www.googleapis.com/auth/youtube'
]

def get_credentials():
    """Get user credentials from session or start OAuth flow"""
    # Check if user has valid credentials in session
    if 'user_credentials' in session:
        try:
            # Reconstruct credentials from session data
            from google.oauth2.credentials import Credentials
            creds_data = session['user_credentials']
            creds = Credentials(
                token=creds_data['token'],
                refresh_token=creds_data['refresh_token'],
                token_uri=creds_data['token_uri'],
                client_id=creds_data['client_id'],
                client_secret=creds_data['client_secret'],
                scopes=creds_data['scopes']
            )
            
            # Check if credentials are still valid
            if creds and creds.valid:
                print("✅ Loaded credentials from session")
                print("✅ Credentials are valid and ready to use")
                return creds
            
            # Refresh if expired
            if creds and creds.expired and creds.refresh_token:
                print("🔄 Refreshing expired credentials...")
                creds.refresh(Request())
                
                # Update session with new token
                session['user_credentials'] = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes
                }
                session.modified = True
                print("✅ Credentials refreshed and updated in session")
                return creds
                
        except Exception as e:
            print(f"❌ Error loading credentials from session: {e}")
            # Clear invalid session data
            session.pop('user_credentials', None)
    
    # No valid credentials in session - start OAuth flow
    print("🔐 No valid credentials in session - starting OAuth flow")
    return None

def authenticate():
    """Start OAuth flow and store credentials in session"""
    try:
        # Load client secrets
        client_secrets_file = os.environ.get('GOOGLE_CREDENTIALS', 'client_secret.json')
        
        if os.environ.get('GOOGLE_CREDENTIALS'):
            # Parse JSON from environment variable
            client_config = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
        else:
            # Load from file
            with open(client_secrets_file, 'r') as f:
                client_config = json.load(f)
        
        # Determine if we're in production
        is_production = request.host_url.startswith('https://')
        
        if is_production:
            # Production: Use web-based OAuth flow
            redirect_uri = 'https://yt-dashboard.onrender.com/auth/google/callback'
            flow = Flow.from_client_config(
                client_config,
                scopes=SCOPES,
                redirect_uri=redirect_uri
            )
            
            # Generate authorization URL
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                prompt='consent'
            )
            
            print(f"🔐 Production OAuth - redirecting to: {auth_url}")
            return auth_url
        else:
            # Development: Use local server
            flow = InstalledAppFlow.from_client_config(
                client_config,
                scopes=SCOPES,
                redirect_uri='http://localhost:8080/'
            )
            
            # Run OAuth flow
            print("🔐 Starting OAuth flow...")
            try:
                creds = flow.run_local_server(port=8080, access_type='offline', prompt='consent')
            except OSError as e:
                if "Address already in use" in str(e):
                    print("🔄 Port 8080 busy, trying port 8081...")
                    creds = flow.run_local_server(port=8081, access_type='offline', prompt='consent')
                else:
                    raise e
            
            # Store credentials in session
            session['user_credentials'] = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes
            }
            session.modified = True
            
            print("✅ OAuth completed - credentials stored in session")
            return creds
        
    except Exception as e:
        print(f"❌ OAuth error: {e}")
        return None

@app.route('/')
def index():
    """Main dashboard page"""
    return app.send_static_file('dashboard.html')

@app.route('/login')
def login():
    """Login page"""
    if 'user_credentials' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/auth/google')
def google_auth():
    """Handle Google OAuth"""
    try:
        print(f"🔐 OAuth request from: {request.host_url}")
        result = authenticate()
        
        # Check if we're in production (result is auth URL) or development (result is creds)
        if isinstance(result, str):
            # Production: redirect to Google OAuth
            print(f"🔐 Production OAuth - redirecting to: {result}")
            return redirect(result)
        elif result:
            # Development: OAuth completed, redirect to dashboard
            print("✅ Development OAuth completed")
            return redirect(url_for('index'))
        else:
            print("❌ Authentication failed - no result")
            flash('Authentication failed. Please try again.', 'error')
            return redirect(url_for('index'))
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        flash('Authentication error. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/auth/google/callback')
def google_auth_callback():
    """Handle Google OAuth callback (production only)"""
    try:
        print(f"🔄 OAuth callback received: {request.url}")
        
        # Load client secrets
        if os.environ.get('GOOGLE_CREDENTIALS'):
            client_config = json.loads(os.environ.get('GOOGLE_CREDENTIALS'))
        else:
            with open('client_secret.json', 'r') as f:
                client_config = json.load(f)
        
        # Create OAuth flow
        flow = InstalledAppFlow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri='https://yt-dashboard.onrender.com/auth/google/callback'
        )
        
        # Exchange authorization code for credentials
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials
        
        # Store credentials in session
        session['user_credentials'] = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
        session.modified = True
        
        print("✅ Production OAuth completed - credentials stored in session")
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"❌ OAuth callback error: {e}")
        flash('Authentication failed. Please try again.', 'error')
        return redirect(url_for('index'))



@app.route('/favicon.ico')
def favicon():
    """Handle favicon requests"""
    return '', 204

@app.route('/privacy')
def privacy():
    """Serve privacy policy page"""
    return app.send_static_file('privacy.html')

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    if request.path == '/favicon.ico':
        return '', 204
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/channel')
def get_channel():
    """Get channel information"""
    if 'user_credentials' not in session:
        return jsonify({'authenticated': False})
    
    try:
        creds = get_credentials()
        if not creds:
            return jsonify({'authenticated': False})
        
        youtube = build('youtube', 'v3', credentials=creds)
        
        # Get channel info
        channels_response = youtube.channels().list(
            part='snippet,statistics',
            mine=True
        ).execute()
        
        if channels_response['items']:
            channel = channels_response['items'][0]
            return jsonify({
                'authenticated': True,
                'title': channel['snippet']['title'],
                'thumbnail': channel['snippet']['thumbnails']['default']['url'],
                'subscriberCount': channel['statistics']['subscriberCount']
            })
        else:
            return jsonify({'authenticated': True, 'error': 'No channel found'}), 404
            
    except Exception as e:
        print(f"Channel API error: {e}")
        return jsonify({'authenticated': False, 'error': str(e)})

@app.route('/api/videos')
def get_videos():
    """Get videos with metrics"""
    if 'user_credentials' not in session:
        return jsonify({'authenticated': False})
    
    try:
        creds = get_credentials()
        if not creds:
            return jsonify({'authenticated': False})
        
        # Get query parameters
        sort_by = request.args.get('sort_by', 'published')
        sort_direction = request.args.get('sort_direction', 'desc')
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        # Check cache first (unless force refresh)
        cache_file = f"videos_cache_{datetime.now().strftime('%Y-%m-%d')}_{'morning' if datetime.now().hour < 12 else 'afternoon'}.json"
        
        if not force_refresh and os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                
                # Check if cache is still valid (6 hours)
                cache_time = datetime.fromisoformat(cached_data.get('cache_time', '2000-01-01'))
                if datetime.now() - cache_time < timedelta(hours=6):
                    # Validate cache structure - check if it has the correct field names
                    videos = cached_data.get('videos', [])
                    if videos and len(videos) > 0:
                        # Check if the first video has the correct field structure
                        first_video = videos[0]
                        required_fields = ['percentWatched', 'watchTime', 'subsGained', 'publishedAt', 'length']
                        if all(field in first_video for field in required_fields):
                            print(f"✅ Using cached data from {cache_file}")
                            
                            # Sort cached data
                            videos = sort_videos(videos, sort_by, sort_direction)
                            
                            return jsonify({
                                'authenticated': True,
                                'videos': videos,
                                'last_updated': cached_data.get('last_updated'),
                                'total_videos_fetched': len(videos),
                                'total_videos_available': cached_data.get('total_videos_available', len(videos))
                            })
                        else:
                            print(f"❌ Cache has invalid structure - missing required fields")
                            # Remove invalid cache file
                            os.remove(cache_file)
                    else:
                        print(f"❌ Cache is empty")
                        # Remove empty cache file
                        os.remove(cache_file)
            except Exception as e:
                print(f"❌ Cache error: {e}")
                # Remove corrupted cache file
                if os.path.exists(cache_file):
                    os.remove(cache_file)
        
        if force_refresh:
            print("🔄 Force refresh requested - clearing cache...")
            if os.path.exists(cache_file):
                os.remove(cache_file)
        
        print("Fetching fresh data from YouTube APIs...")
        
        # Build YouTube API client
        youtube = build('youtube', 'v3', credentials=creds)
        youtube_analytics = build('youtubeAnalytics', 'v2', credentials=creds)
        
        # Get all videos
        search_request = youtube.search().list(
            part='snippet',
            forMine=True,
            type='video',
            maxResults=50,
            order='date'
        )
        
        response = search_request.execute()
        
        if not response.get('items'):
            return jsonify({'videos': [], 'error': 'No videos found'})
        
        # Get all video IDs
        all_video_items = response.get("items", [])
        video_ids = [item["id"]["videoId"] for item in all_video_items]
        total_videos_fetched = len(video_ids)
        
        print(f"Fetching metrics for {total_videos_fetched} videos")
        
        # Get detailed video info
        videos_request = youtube.videos().list(
            part='snippet,contentDetails,statistics,status',
            id=','.join(video_ids)
        )
        videos_response = videos_request.execute()
        
        # Get analytics data for each video
        videos_with_metrics = []
        for i, video in enumerate(videos_response.get('items', []), 1):
            video_id = video['id']
            print(f"Processing video {i}/{total_videos_fetched}: {video_id}")
            
            try:
                metrics = get_video_metrics(youtube_analytics, video_id)
                
                # Calculate video length
                duration = isodate.parse_duration(video['contentDetails']['duration'])
                video_length = f"{int(duration.total_seconds() // 60):02d}:{int(duration.total_seconds() % 60):02d}"
                
                # Calculate % watched
                avg_view_duration = metrics.get('averageViewDuration', 0)
                total_duration = duration.total_seconds()
                percent_watched = (avg_view_duration / total_duration * 100) if total_duration > 0 else 0
                
                video_data = {
                    'id': video_id,
                    'title': video['snippet']['title'],
                    'thumbnail': video['snippet']['thumbnails']['medium']['url'],
                    'publishedAt': video['snippet']['publishedAt'],
                    'views': metrics.get('views', 0),
                    'likes': metrics.get('likes', 0),
                    'length': video_length,
                    'watchTime': f"{int(avg_view_duration // 60):02d}:{int(avg_view_duration % 60):02d}",
                    'percentWatched': round(percent_watched, 1),
                    'subsGained': metrics.get('subscribersGained', 0)
                }
                
                videos_with_metrics.append(video_data)
                print(f"  ✅ Success (attempt 1)")
                
            except Exception as e:
                print(f"  ❌ Error processing video {video_id}: {e}")
                continue
        
        print(f"✅ Successfully processed {len(videos_with_metrics)}/{total_videos_fetched} videos")
        
        # Sort videos
        videos_with_metrics = sort_videos(videos_with_metrics, sort_by, sort_direction)
        
        # Calculate last updated (yesterday's date)
        last_updated = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Cache the results
        cache_data = {
            'videos': videos_with_metrics,
            'last_updated': last_updated,
            'total_videos_available': total_videos_fetched,
            'cache_time': datetime.now().isoformat()
        }
        
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
        
        print(f"Saved cache: {cache_file}")
        
        return jsonify({
            'authenticated': True,
            'videos': videos_with_metrics,
            'last_updated': last_updated,
            'total_videos_fetched': len(videos_with_metrics),
            'total_videos_available': total_videos_fetched
        })
        
    except Exception as e:
        print(f"❌ Unhandled exception: {e}")
        print(f"❌ Exception type: {type(e).__name__}")
        print(f"❌ Traceback: {e}")
        return jsonify({'error': str(e)}), 500

def get_video_metrics(youtube_analytics, video_id):
    """Get analytics metrics for a single video"""
    try:
        # Query YouTube Analytics API for views, likes, and average view duration
        request = youtube_analytics.reports().query(
            ids=f'channel==MINE',
            startDate='2024-01-01',
            endDate=datetime.now().strftime('%Y-%m-%d'),
            metrics='views,likes,averageViewDuration',
            dimensions='video',
            filters=f'video=={video_id}'
        )
        
        response = request.execute()
        
        # Initialize metrics
        metrics = {
            'views': 0,
            'likes': 0,
            'averageViewDuration': 0,
            'subscribersGained': 0
        }
        
        if response.get('rows'):
            row = response['rows'][0]
            metrics['views'] = row[1]
            metrics['likes'] = row[2]
            metrics['averageViewDuration'] = row[3]
        
        # Query for subscribers gained (separate query due to API limitations)
        try:
            subs_request = youtube_analytics.reports().query(
                ids=f'channel==MINE',
                startDate='2024-01-01',
                endDate=datetime.now().strftime('%Y-%m-%d'),
                metrics='subscribersGained',
                dimensions='video',
                filters=f'video=={video_id}'
            )
            
            subs_response = subs_request.execute()
            
            if subs_response.get('rows'):
                subs_row = subs_response['rows'][0]
                metrics['subscribersGained'] = subs_row[1]
                
        except Exception as subs_error:
            print(f"  ⚠️ Could not fetch subscribers gained for {video_id}: {subs_error}")
            # Keep default value of 0
        
        return metrics
            
    except Exception as e:
        print(f"  ❌ Analytics API error for {video_id}: {e}")
        return {
            'views': 0,
            'likes': 0,
            'averageViewDuration': 0,
            'subscribersGained': 0
        }

def sort_videos(videos, sort_by, sort_direction):
    """Sort videos by specified field and direction"""
    reverse = sort_direction == 'desc'
    
    if sort_by == 'published':
        return sorted(videos, key=lambda x: x['publishedAt'], reverse=reverse)
    elif sort_by == 'views':
        return sorted(videos, key=lambda x: x['views'], reverse=reverse)
    elif sort_by == 'likes':
        return sorted(videos, key=lambda x: x['likes'], reverse=reverse)
    elif sort_by == 'watched':
        return sorted(videos, key=lambda x: x['percentWatched'], reverse=reverse)
    elif sort_by == 'length':
        return sorted(videos, key=lambda x: x['length'], reverse=reverse)
    elif sort_by == 'watchTime':
        return sorted(videos, key=lambda x: x['watchTime'], reverse=reverse)
    elif sort_by == 'subsGained':
        return sorted(videos, key=lambda x: x['subsGained'], reverse=reverse)
    else:
        return videos

@app.route('/api/clear-cache')
def clear_cache():
    """Clear all cache files"""
    if 'user_credentials' not in session:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        cache_files = [f for f in os.listdir('.') if f.startswith('videos_cache_') and f.endswith('.json')]
        for cache_file in cache_files:
            os.remove(cache_file)
            print(f"🗑️ Deleted cache file: {cache_file}")
        
        return jsonify({'message': f'Cleared {len(cache_files)} cache files'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    """Global error handler"""
    print(f"❌ Unhandled exception: {e}")
    print(f"❌ Exception type: {type(e).__name__}")
    print(f"❌ Traceback: {e}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000, use_reloader=False) 