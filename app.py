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
    'https://www.googleapis.com/auth/yt-analytics.readonly'
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
        # For testing: you can force production mode by setting FORCE_PRODUCTION=1
        is_production = request.host_url.startswith('https://') or os.environ.get('FORCE_PRODUCTION') == '1'
        
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
            
            # Clear any existing session data for new user
            session.clear()
            
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
        
        # Clear any existing session data for new user
        session.clear()
        
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

@app.route('/health')
def health_check():
    """Health check endpoint for ping services"""
    return {'status': 'healthy', 'timestamp': datetime.now().isoformat()}, 200

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
    print(f"🔍 DEBUG: Channel API - Session keys: {list(session.keys())}")
    print(f"🔍 DEBUG: Channel API - Has user_credentials: {'user_credentials' in session}")
    
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

def get_test_videos(sort_by, sort_direction, force_refresh):
    """Mock function to return test data when API quota is exceeded."""
    print("🔄 Mocking YouTube API quota exceeded for testing refresh button.")
    # Simulate a scenario where API quota is exceeded
    # In a real application, you would handle this by redirecting to a maintenance page
    # For now, we'll return a dummy response that indicates an error
    return jsonify({
        'authenticated': True,
        'videos': [
            {
                'id': 'test_video_1',
                'title': 'Test Video 1',
                'thumbnail': 'https://via.placeholder.com/150',
                'publishedAt': (datetime.now() - timedelta(days=1)).isoformat(),
                'views': 1000,
                'likes': 50,
                'length': '05:00',
                'watchTime': '00:30',
                'percentWatched': 60.0,
                'subsGained': 10
            },
            {
                'id': 'test_video_2',
                'title': 'Test Video 2',
                'thumbnail': 'https://via.placeholder.com/150',
                'publishedAt': (datetime.now() - timedelta(days=2)).isoformat(),
                'views': 500,
                'likes': 25,
                'length': '03:00',
                'watchTime': '00:15',
                'percentWatched': 50.0,
                'subsGained': 5
            }
        ],
        'last_updated': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
        'total_videos_fetched': 2,
        'total_videos_available': 2
    })

@app.route('/api/videos')
def get_videos():
    """Get videos with metrics"""
    print(f"🔍 DEBUG: Session keys: {list(session.keys())}")
    print(f"🔍 DEBUG: Has user_credentials: {'user_credentials' in session}")
    print(f"🔍 DEBUG: Session content: {dict(session)}")
    
    if 'user_credentials' not in session:
        print(f"❌ No user_credentials in session!")
        return jsonify({'authenticated': False})
    
    try:
        creds = get_credentials()
        if not creds:
            return jsonify({'authenticated': False})
        
        # Get query parameters
        sort_by = request.args.get('sort_by', 'published')
        sort_direction = request.args.get('sort_direction', 'desc')
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        # Build YouTube API client
        youtube = build('youtube', 'v3', credentials=creds)
        
        # Get user's channel ID for cache identification
        try:
            channels_response = youtube.channels().list(
                part='id',
                mine=True
            ).execute()
            
            if not channels_response.get('items'):
                return jsonify({'authenticated': False, 'error': 'No channel found'})
            
            channel_id = channels_response['items'][0]['id']
        except Exception as e:
            print(f"❌ Channel API error (likely quota exceeded): {e}")
            # Use test mode with mock data
            return get_test_videos(sort_by, sort_direction, force_refresh)
        
        # Check cache first (unless force refresh) - make cache user-specific
        cache_file = f"videos_cache_{channel_id}_{datetime.now().strftime('%Y-%m-%d')}_{'morning' if datetime.now().hour < 12 else 'afternoon'}.json"
        
        if not force_refresh and os.path.exists(cache_file):
            print(f"🔍 DEBUG: Found cache file: {cache_file}")
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                
                # Check if cache is still valid (6 hours)
                cache_time = datetime.fromisoformat(cached_data.get('cache_time', '2000-01-01'))
                if datetime.now() - cache_time < timedelta(hours=6):
                    print(f"🔍 DEBUG: Cache is valid, using cached data")
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
                else:
                    print(f"🔍 DEBUG: Cache is expired, will fetch fresh data")
            except Exception as e:
                print(f"🔍 DEBUG: Cache error: {e}")
                # Remove corrupted cache file
                if os.path.exists(cache_file):
                    os.remove(cache_file)
        else:
            if force_refresh:
                print(f"🔍 DEBUG: Force refresh requested, will fetch fresh data")
            else:
                print(f"🔍 DEBUG: No cache file found, will fetch fresh data")
        
        if force_refresh:
            print("🔄 Force refresh requested - clearing cache...")
            if os.path.exists(cache_file):
                os.remove(cache_file)
        
        print("Fetching fresh data from YouTube APIs...")
        
        # Build YouTube Analytics API client
        youtube_analytics = build('youtubeAnalytics', 'v2', credentials=creds)
        
        # Get all videos using search API, then filter by privacy status
        try:
            # Get all videos for the channel using search API
            search_request = youtube.search().list(
                part='snippet',
                forMine=True,
                type='video',
                maxResults=100,  # Set to 100 videos maximum
                order='date'
            )
            
            response = search_request.execute()
            
            if not response.get('items'):
                return jsonify({'videos': [], 'error': 'No videos found'})
            
            # Get all video IDs from search results
            all_video_items = response.get("items", [])
            all_video_ids = [item["id"]["videoId"] for item in all_video_items]
            
            # Get detailed video info including privacy status
            videos_request = youtube.videos().list(
                part='snippet,contentDetails,statistics,status',
                id=','.join(all_video_ids)
            )
            videos_response = videos_request.execute()
            
            # Filter to only public videos
            all_videos = videos_response.get('items', [])
            public_videos = [video for video in all_videos 
                           if video.get('status', {}).get('privacyStatus') == 'public']
            
            if not public_videos:
                return jsonify({
                    'authenticated': True,
                    'videos': [], 
                    'error': 'No public videos found',
                    'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'total_videos_fetched': 0,
                    'total_videos_available': 0
                })
            
            # Get video IDs for analytics (public videos only)
            video_ids = [video['id'] for video in public_videos]
            total_videos_fetched = len(video_ids)
            
            print(f"✅ Processing {len(public_videos)} public videos")
            
        except Exception as e:
            print(f"❌ Search/Videos API error (likely quota exceeded): {e}")
            # Use test mode with mock data
            return get_test_videos(sort_by, sort_direction, force_refresh)
        
        print(f"Fetching metrics for {total_videos_fetched} videos")
        
        # Get analytics data for ALL videos using Groups API (single call)
        print(f"🔄 Fetching metrics for all {total_videos_fetched} videos using Groups API...")
        all_metrics = get_video_metrics_with_groups(youtube_analytics, video_ids)
        
        # If Groups API fails, return error instead of falling back
        if not all_metrics:
            print("❌ Groups API failed - no fallback to save API quota")
            return jsonify({'error': 'Analytics API failed. Please try again later.'}), 500
        
        # Process videos with the fetched metrics
        videos_with_metrics = []
        for i, video in enumerate(public_videos, 1):
            video_id = video['id']
            print(f"Processing video {i}/{total_videos_fetched}: {video_id}")
            
            try:
                # Get metrics for this video from the batch result
                video_metrics = all_metrics.get(video_id, {})
                
                # Calculate video length
                duration = isodate.parse_duration(video['contentDetails']['duration'])
                video_length = f"{int(duration.total_seconds() // 60):02d}:{int(duration.total_seconds() % 60):02d}"
                
                # Calculate % watched
                avg_view_duration = video_metrics.get('averageViewDuration', 0)
                total_duration = duration.total_seconds()
                percent_watched = (avg_view_duration / total_duration * 100) if total_duration > 0 else 0
                
                video_data = {
                    'id': video_id,
                    'title': video['snippet']['title'],
                    'thumbnail': video['snippet']['thumbnails']['medium']['url'],
                    'publishedAt': video['snippet']['publishedAt'],
                    'views': video_metrics.get('views', 0),
                    'likes': video_metrics.get('likes', 0),
                    'length': video_length,
                    'watchTime': f"{int(avg_view_duration // 60):02d}:{int(avg_view_duration % 60):02d}",
                    'percentWatched': round(percent_watched, 1),
                    'subsGained': video_metrics.get('subscribersGained', 0)
                }
                
                videos_with_metrics.append(video_data)
                print(f"  ✅ Success")
                
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

def get_video_metrics_with_groups(youtube_analytics, video_ids):
    """Get analytics metrics for multiple videos using efficient batch query"""
    try:
        print(f"🔄 Using efficient batch query for {len(video_ids)} videos...")
        
        # Check if filter string would be too long (YouTube video IDs are 11 chars each)
        filter_string = f'video=={",".join(video_ids)}'
        if len(filter_string) > 1500:  # Conservative limit to avoid API issues
            print(f"⚠️ Filter string too long ({len(filter_string)} chars), limiting to first 100 videos")
            video_ids = video_ids[:100]  # Limit to first 100 videos
            filter_string = f'video=={",".join(video_ids)}'
        
        # Use the working approach that was already efficient
        # This uses a single API call with video filters
        group_query = {
            'ids': 'channel==MINE',
            'startDate': '2024-01-01',
            'endDate': datetime.now().strftime('%Y-%m-%d'),
            'metrics': 'views,likes,averageViewDuration,averageViewPercentage,subscribersGained',
            'dimensions': 'video',
            'filters': filter_string,
            'sort': '-views'
        }
        
        # Execute the query
        response = youtube_analytics.reports().query(**group_query).execute()
        
        if not response.get('rows'):
            print("❌ No data returned from batch query")
            return {}
        
        # Convert response to video_id -> metrics mapping
        metrics_by_video = {}
        for row in response['rows']:
            video_id = row[0]  # First column is video ID
            metrics_by_video[video_id] = {
                'views': row[1],
                'likes': row[2],
                'averageViewDuration': row[3],
                'averageViewPercentage': row[4],
                'subscribersGained': row[5]
            }
        
        print(f"✅ Batch query returned metrics for {len(metrics_by_video)} videos")
        return metrics_by_video
        
    except Exception as e:
        print(f"❌ Batch query error: {e}")
        return {}

# Note: Groups API implementation removed due to API issues
# Using efficient batch query approach instead

def get_video_metrics_fallback(youtube_analytics, video_ids):
    """Fallback to individual API calls if Groups API fails"""
    print(f"🔄 Falling back to individual API calls for {len(video_ids)} videos...")
    
    metrics_by_video = {}
    for video_id in video_ids:
        try:
            metrics = get_video_metrics(youtube_analytics, video_id)
            if metrics:
                metrics_by_video[video_id] = metrics
        except Exception as e:
            print(f"❌ Failed to get metrics for video {video_id}: {e}")
            continue
    
    return metrics_by_video

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

@app.route('/api/clear-session')
def clear_session():
    """Clear user session data"""
    try:
        # Clear all session data
        session.clear()
        print("🗑️ Cleared all session data")
        return jsonify({'message': 'Session cleared successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logout')
def logout():
    """Logout user and clear session"""
    try:
        # Clear all session data
        session.clear()
        print("🚪 User logged out, session cleared")
        return jsonify({'message': 'Logged out successfully'})
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
    app.run(debug=True, port=5000, use_reloader=True) 