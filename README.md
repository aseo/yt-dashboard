# YouTube Analytics Dashboard

A modern, local web dashboard for analyzing your YouTube video metrics. Built with Flask, Tailwind CSS, and Chart.js.

## Features

- 📊 **Real-time Analytics**: View your latest video performance metrics
- 📈 **Interactive Charts**: Visualize views, engagement rates, and trends
- 🎯 **Key Metrics**: Total views, likes, subscribers gained, and average watch time
- 📱 **Responsive Design**: Works great on desktop and mobile devices
- 🔄 **Auto-refresh**: Keep your data up to date with the refresh button
- 🎨 **Modern UI**: Beautiful gradient design with hover effects

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Google API Setup**:
   - Make sure you have `client_secret.json` in your project directory
   - The app will automatically authenticate on first run
   - Your authentication token will be saved in `token.json`

3. **Run the Dashboard**:
   ```bash
   python app.py
   ```

4. **Access the Dashboard**:
   Open your browser and go to `http://localhost:5000`

## API Endpoints

- `GET /` - Main dashboard page
- `GET /api/videos` - Get video analytics data
- `GET /api/channel` - Get channel information

## Data Sources

The dashboard pulls data from:
- **YouTube Data API v3**: Basic video information and statistics
- **YouTube Analytics API v2**: Detailed analytics metrics

## Metrics Tracked

- **Views**: Total view count per video
- **Likes**: Total likes per video
- **Average View Duration**: How long viewers watch on average
- **Average View Percentage**: Percentage of video watched
- **Subscribers Gained**: New subscribers from each video
- **Video Length**: Duration of each video
- **Publish Date**: When each video was published

## Customization

You can easily customize the dashboard by:
- Modifying the date range in `app.py` (currently set to 2025-01-01 to today)
- Adding new metrics to the analytics API calls
- Styling the frontend with Tailwind CSS classes
- Adding new chart types using Chart.js

## Troubleshooting

- **Authentication Issues**: Delete `token.json` and restart the app to re-authenticate
- **No Data**: Make sure your videos have analytics data available (may take time for new videos)
- **API Quotas**: Be mindful of YouTube API quotas for large channels

## Technologies Used

- **Backend**: Flask (Python)
- **Frontend**: HTML5, Tailwind CSS, Chart.js
- **APIs**: YouTube Data API v3, YouTube Analytics API v2
- **Icons**: Font Awesome 