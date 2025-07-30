# Deployment Guide

## 🔒 Security First!

### Before Deploying:
1. **Never commit sensitive files** - They're already in `.gitignore`
2. **Use environment variables** for all credentials
3. **Generate strong SECRET_KEY**
4. **Update OAuth redirect URIs** in Google Cloud Console

## Render Deployment (Recommended)

### 1. Prepare Your Code
- ✅ All files are ready for deployment
- ✅ `requirements.txt` includes gunicorn
- ✅ `wsgi.py` entry point created
- ✅ `config.py` handles environments
- ✅ **Security updates applied**

### 2. Create Render Account
1. Go to [render.com](https://render.com)
2. Sign up with GitHub
3. Create new Web Service

### 3. Connect GitHub Repository
1. Connect your GitHub repo
2. Select the repository
3. Render will auto-detect Python

### 4. Configure Environment Variables
Add these in Render dashboard:

#### **Required Environment Variables:**
```
FLASK_ENV=production
SECRET_KEY=your-very-long-random-secret-key-here
GOOGLE_CREDENTIALS={"token":"...","refresh_token":"...","token_uri":"...","client_id":"...","client_secret":"...","scopes":[...]}
```

#### **How to Get GOOGLE_CREDENTIALS:**
1. **Copy your token.json content** (the entire JSON)
2. **Paste it as GOOGLE_CREDENTIALS** in Render
3. **Make sure it's valid JSON** (no line breaks)

### 5. Configure Build Settings
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn wsgi:app`
- **Python Version**: 3.9 or higher

### 6. Deploy
- Click "Create Web Service"
- Render will build and deploy automatically
- Your app will be available at `https://youtube-analytics-dashboard.onrender.com`

### 7. Update OAuth Redirect URIs
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Go to "APIs & Services" > "Credentials"
4. Edit your OAuth 2.0 Client ID
5. Add to "Authorized redirect URIs":
   - `https://youtube-analytics-dashboard.onrender.com/oauth2callback`
6. Save changes

## Security Checklist

### ✅ Before Deployment:
- [ ] Sensitive files in `.gitignore`
- [ ] Strong SECRET_KEY generated
- [ ] GOOGLE_CREDENTIALS environment variable set
- [ ] OAuth redirect URIs updated
- [ ] HTTPS enabled (Render provides this)

### ✅ After Deployment:
- [ ] App loads without errors
- [ ] OAuth flow works (if needed)
- [ ] API calls work
- [ ] No sensitive data in logs

## Troubleshooting

### Common Issues:
1. **"Authentication required" error**: Check GOOGLE_CREDENTIALS format
2. **OAuth redirect error**: Update redirect URIs in Google Cloud Console
3. **Build fails**: Check requirements.txt and Python version

### Testing Locally:
```bash
# Test with environment variables
export FLASK_ENV=production
export SECRET_KEY=test-secret-key
export GOOGLE_CREDENTIALS='{"token":"...","refresh_token":"..."}'
python app.py
``` 