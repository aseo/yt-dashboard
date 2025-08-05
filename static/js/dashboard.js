let videosData = [];
let currentSort = { column: 'published', direction: 'desc' };
let totalVideosFetched = 0;
let totalVideosAvailable = 0;

// Anti-spam variables
let lastRefreshTime = 0;
const REFRESH_COOLDOWN = 30000; // 30 seconds cooldown
let refreshCount = 0;
const MAX_REFRESHES_PER_HOUR = 10; // Max 10 refreshes per hour

// Format numbers with commas
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

// Toast notification function
function showToast(message, type = 'info') {
    // Remove existing toast
    const existingToast = document.getElementById('toast');
    if (existingToast) {
        existingToast.remove();
    }
    
    // Create toast element
    const toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = `fixed top-4 right-4 z-50 px-6 py-3 rounded-lg shadow-lg text-white font-medium transition-all duration-300 transform translate-x-full`;
    
    // Set color based on type
    switch (type) {
        case 'success':
            toast.className += ' bg-green-600';
            break;
        case 'error':
            toast.className += ' bg-red-600';
            break;
        case 'warning':
            toast.className += ' bg-yellow-600';
            break;
        default:
            toast.className += ' bg-blue-600';
    }
    
    toast.textContent = message;
    document.body.appendChild(toast);
    
    // Animate in
    setTimeout(() => {
        toast.classList.remove('translate-x-full');
    }, 100);
    
    // Auto remove after 4 seconds
    setTimeout(() => {
        toast.classList.add('translate-x-full');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 300);
    }, 4000);
}

// Format date from ISO string
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric' 
    });
}

// Format duration from seconds
function formatDuration(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

// Get watch percentage color based on video length
function getWatchPercentageColor(watchPercent, videoLength) {
    // Parse video length from "MM:SS" format
    const parts = videoLength.split(':');
    const lengthInSeconds = parseInt(parts[0]) * 60 + parseInt(parts[1]);
    
    // Define benchmarks based on video length (Shorts vs Long-Form)
    let needsImprovementThreshold, goodThreshold, greatThreshold;
    
    // Shorts benchmarks (under 60 seconds)
    if (lengthInSeconds < 10) {
        needsImprovementThreshold = 80;
        goodThreshold = 80;
        greatThreshold = 100;
    } else if (lengthInSeconds < 20) {
        needsImprovementThreshold = 70;
        goodThreshold = 70;
        greatThreshold = 90;
    } else if (lengthInSeconds < 40) {
        needsImprovementThreshold = 60;
        goodThreshold = 60;
        greatThreshold = 80;
    } else if (lengthInSeconds < 60) {
        needsImprovementThreshold = 50;
        goodThreshold = 50;
        greatThreshold = 70;
    }
    // Long-form benchmarks (60+ seconds)
    else if (lengthInSeconds <= 180) { // 1-3 minutes
        needsImprovementThreshold = 50;
        goodThreshold = 50;
        greatThreshold = 70;
    } else if (lengthInSeconds <= 300) { // 3-5 minutes
        needsImprovementThreshold = 40;
        goodThreshold = 40;
        greatThreshold = 60;
    } else if (lengthInSeconds <= 600) { // 5-10 minutes
        needsImprovementThreshold = 30;
        goodThreshold = 30;
        greatThreshold = 50;
    } else if (lengthInSeconds <= 900) { // 10-15 minutes
        needsImprovementThreshold = 25;
        goodThreshold = 25;
        greatThreshold = 45;
    } else { // 15+ minutes
        needsImprovementThreshold = 20;
        goodThreshold = 20;
        greatThreshold = 40;
    }
    
    if (watchPercent >= greatThreshold) {
        return 'text-blue-600 font-bold'; // Blue for great
    } else if (watchPercent >= goodThreshold) {
        return 'text-green-600 font-semibold'; // Green for good
    } else {
        return 'text-orange-600 font-semibold'; // Orange for needs improvement
    }
}

// Logout function
async function logout() {
    try {
        const response = await fetch('/api/logout', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            // Clear the page and show sign in state
            location.reload();
        } else {
            showToast('Logout failed. Please try again.', 'error');
        }
    } catch (error) {
        console.error('Logout error:', error);
        showToast('Logout failed. Please try again.', 'error');
    }
}

// Load channel information
async function loadChannelInfo() {
    // Hide logout button initially
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.style.display = 'none';
    }
    
    try {
        const response = await fetch('/api/channel');
        const data = await response.json();
        
        const channelInfo = document.getElementById('channel-info');
        
        if (data.authenticated) {
            // User is authenticated - show channel info
            channelInfo.innerHTML = `
                <div class="flex items-center space-x-2">
                    <img class="w-8 h-8 rounded-full" src="${data.thumbnail}" alt="${data.title}">
                    <div class="font-medium">${data.title}</div>
                </div>
            `;
            // Show logout button
            const logoutBtn = document.getElementById('logout-btn');
            if (logoutBtn) {
                logoutBtn.style.display = 'block';
            }
        } else {
            // User is not authenticated - show sign in button
            channelInfo.innerHTML = `
                <a href="/auth/google" class="text-white hover:text-blue-200 transition-colors text-sm flex items-center">
                    <i class="fas fa-sign-in-alt mr-1"></i>
                    Sign In
                </a>
            `;
            // Hide logout button
            const logoutBtn = document.getElementById('logout-btn');
            if (logoutBtn) {
                logoutBtn.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error loading channel info:', error);
        const channelInfo = document.getElementById('channel-info');
        channelInfo.innerHTML = `
            <div class="text-red-300 text-sm">
                <i class="fas fa-exclamation-triangle mr-1"></i>
                Connection error
            </div>
        `;
    }
}

// Refresh data function
async function refreshData() {
    const refreshBtn = document.getElementById('refresh-btn');
    const icon = refreshBtn.querySelector('i');
    
    // Check cooldown period
    const now = Date.now();
    const timeSinceLastRefresh = now - lastRefreshTime;
    
    if (timeSinceLastRefresh < REFRESH_COOLDOWN) {
        const remainingTime = Math.ceil((REFRESH_COOLDOWN - timeSinceLastRefresh) / 1000);
        showToast(`Please wait ${remainingTime} seconds before refreshing again`, 'warning');
        return;
    }
    
    // Check hourly limit
    if (refreshCount >= MAX_REFRESHES_PER_HOUR) {
        showToast('Refresh limit reached. Please wait an hour before refreshing again.', 'error');
        return;
    }
    
    // Show loading state
    icon.className = 'fas fa-spinner fa-spin';
    refreshBtn.disabled = true;
    
    try {
        // Force refresh by setting refresh=true
        await loadVideos(true);
        
        // Update anti-spam counters
        lastRefreshTime = now;
        refreshCount++;
        
        // Reset refresh count after 1 hour
        setTimeout(() => {
            refreshCount = Math.max(0, refreshCount - 1);
        }, 3600000); // 1 hour
        
        // Show success state briefly
        icon.className = 'fas fa-check text-green-600';
        showToast('Data refreshed successfully!', 'success');
        setTimeout(() => {
            icon.className = 'fas fa-sync-alt';
            refreshBtn.disabled = false;
        }, 1000);
        
    } catch (error) {
        console.error('Error refreshing data:', error);
        
        // Show error state
        icon.className = 'fas fa-exclamation-triangle text-red-600';
        showToast('Failed to refresh data. Please try again later.', 'error');
        setTimeout(() => {
            icon.className = 'fas fa-sync-alt';
            refreshBtn.disabled = false;
        }, 2000);
    }
}

// Load videos data
async function loadVideos(forceRefresh = false) {
    try {
        // Show loading state
        document.getElementById('videos-table').innerHTML = `
            <tr>
                <td colspan="8" class="px-6 py-8 text-center">
                    <div class="flex flex-col items-center justify-center space-y-2">
                        <div class="flex items-center space-x-2">
                            <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                            <span class="text-gray-600">Loading videos...</span>
                        </div>
                        <div class="text-sm text-gray-500">Retrieving up to 50 videos</div>
                    </div>
                </td>
            </tr>
        `;
        
        const url = `/api/videos?sort_by=${currentSort.column}&sort_direction=${currentSort.direction}&refresh=${forceRefresh}`;
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.authenticated) {
            // User is authenticated - handle video data
            if (data.videos && data.last_updated) {
                videosData = data.videos;
                totalVideosFetched = data.total_videos_fetched || data.videos.length;
                totalVideosAvailable = data.total_videos_available || data.videos.length;
                
                // Last updated timestamp removed - now showing static API delay message
                
                // Update video count indicator
                updateVideoCount();
                
                // Show cache status if available
                if (data.cached) {
                    console.log('📦 Loaded from cache - fast response!');
                } else {
                    console.log('🔄 Fresh data loaded from YouTube APIs');
                }
                
                // Check if there are no videos
                if (data.videos.length === 0) {
                    document.getElementById('videos-table').innerHTML = `
                        <tr>
                            <td colspan="8" class="px-6 py-12 text-center">
                                <div class="flex flex-col items-center space-y-6">
                                    <div class="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center">
                                        <i class="fas fa-video-slash text-gray-400 text-2xl"></i>
                                    </div>
                                    <div class="text-center">
                                        <h3 class="text-lg font-medium text-gray-900 mb-2">No public videos found</h3>
                                        <p class="text-gray-500 mb-6">This channel doesn't have any publicly published videos, or all videos are private/unlisted.</p>
                                        <button onclick="refreshData()" class="inline-flex items-center px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors">
                                            <i class="fas fa-sync-alt mr-2"></i>
                                            Try Again
                                        </button>
                                    </div>
                                </div>
                            </td>
                        </tr>
                    `;
                } else {
                    updateTable();
                }
            } else {
                // Fallback for old data structure
                videosData = data;
                totalVideosFetched = data.length;
                totalVideosAvailable = data.length;
                updateTable();
            }
        } else {
            // User is not authenticated - show sign in placeholder
            document.getElementById('videos-table').innerHTML = `
                <tr>
                    <td colspan="8" class="px-6 py-12 text-center">
                        <div class="flex flex-col items-center space-y-6">
                            <div class="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center">
                                <i class="fas fa-chart-line text-blue-600 text-2xl"></i>
                            </div>
                            <div class="text-center">
                                <h3 class="text-lg font-medium text-gray-900 mb-2">Sign in to view your YouTube analytics</h3>
                                <p class="text-gray-500 mb-6">Connect your Google account to see detailed metrics for your videos</p>
                                <a href="/auth/google" class="inline-flex items-center px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors" onclick="console.log('Sign In clicked in table'); return true;">
                                    <i class="fab fa-google mr-2"></i>
                                    Sign in with Google
                                </a>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
            
            // Update video count to show sign in message
            updateVideoCount();
        }
    } catch (error) {
        console.error('Error loading videos:', error);
        
        document.getElementById('videos-table').innerHTML = `
            <tr>
                <td colspan="8" class="px-6 py-4 text-center text-red-500">
                    Error loading videos. Please try again.
                </td>
            </tr>
        `;
    }
}

// Update video count indicator
function updateVideoCount() {
    const countElement = document.getElementById('video-count');
    if (countElement) {
        if (totalVideosFetched === 0 && totalVideosAvailable === 0) {
            // Check if user is authenticated but has no videos
            if (videosData && videosData.length === 0) {
                countElement.textContent = 'No public videos found';
                countElement.className = 'text-sm text-gray-500';
            } else {
                // User is not authenticated
                countElement.textContent = 'Sign in to view your videos';
                countElement.className = 'text-sm text-gray-500';
            }
        } else if (totalVideosAvailable > totalVideosFetched) {
            countElement.textContent = `Showing ${totalVideosFetched} of ${totalVideosAvailable} videos`;
            countElement.className = 'text-sm text-gray-600';
        } else {
            countElement.textContent = `Showing ${totalVideosFetched} videos`;
            countElement.className = 'text-sm text-gray-600';
        }
    }
}

// Update refresh button status
function updateRefreshButtonStatus() {
    const refreshBtn = document.getElementById('refresh-btn');
    const icon = refreshBtn.querySelector('i');
    const now = Date.now();
    const timeSinceLastRefresh = now - lastRefreshTime;
    
    if (timeSinceLastRefresh < REFRESH_COOLDOWN) {
        const remainingTime = Math.ceil((REFRESH_COOLDOWN - timeSinceLastRefresh) / 1000);
        refreshBtn.title = `Refresh available in ${remainingTime} seconds`;
        refreshBtn.classList.add('opacity-50', 'cursor-not-allowed');
        icon.className = 'fas fa-clock text-gray-400';
    } else if (refreshCount >= MAX_REFRESHES_PER_HOUR) {
        refreshBtn.title = 'Refresh limit reached (10 per hour)';
        refreshBtn.classList.add('opacity-50', 'cursor-not-allowed');
        icon.className = 'fas fa-ban text-red-400';
    } else {
        refreshBtn.title = 'Refresh data';
        refreshBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        icon.className = 'fas fa-sync-alt';
    }
}

// Sort videos function
function sortVideos(column, direction) {
    videosData.sort((a, b) => {
        let aVal, bVal;
        
        switch(column) {
            case 'title':
                aVal = a.title.toLowerCase();
                bVal = b.title.toLowerCase();
                break;
            case 'published':
                aVal = new Date(a.publishedAt);
                bVal = new Date(b.publishedAt);
                break;
            case 'views':
                aVal = a.views;
                bVal = b.views;
                break;
            case 'likes':
                aVal = a.likes;
                bVal = b.likes;
                break;
            case 'length':
                aVal = parseInt(a.length.split(':')[0]) * 60 + parseInt(a.length.split(':')[1]);
                bVal = parseInt(b.length.split(':')[0]) * 60 + parseInt(b.length.split(':')[1]);
                break;
            case 'watchTime':
                aVal = parseInt(a.watchTime.split(':')[0]) * 60 + parseInt(a.watchTime.split(':')[1]);
                bVal = parseInt(b.watchTime.split(':')[0]) * 60 + parseInt(b.watchTime.split(':')[1]);
                break;
            case 'watched':
                aVal = a.percentWatched;
                bVal = b.percentWatched;
                break;
            case 'subs':
                aVal = a.subsGained;
                bVal = b.subsGained;
                break;
            default:
                return 0;
        }
        
        if (direction === 'asc') {
            return aVal > bVal ? 1 : -1;
        } else {
            return aVal < bVal ? 1 : -1;
        }
    });
}

// Sort table function
function sortTable(column) {
    // Toggle direction if same column, otherwise set to desc
    if (currentSort.column === column) {
        currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
        currentSort.column = column;
        currentSort.direction = 'desc';
    }
    
    // Update sort icons
    updateSortIcons(column, currentSort.direction);
    
    // Load videos with new sort
    loadVideos();
}



// Update sort icons
function updateSortIcons(activeColumn, direction) {
    const columns = ['title', 'published', 'views', 'likes', 'length', 'watchTime', 'watched', 'subs'];
    
    columns.forEach(col => {
        const icon = document.getElementById(`sort-${col}`);
        if (col === activeColumn) {
            icon.className = direction === 'asc' ? 'fas fa-sort-up ml-1 text-blue-600' : 'fas fa-sort-down ml-1 text-blue-600';
        } else {
            icon.className = 'fas fa-sort ml-1 text-gray-400';
        }
    });
}

// Update videos table
function updateTable() {
    const tbody = document.getElementById('videos-table');
    
    if (!videosData.length) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="px-6 py-4 text-center text-gray-500">
                    No videos found.
                </td>
            </tr>
        `;
        return;
    }
    
    // Display all videos
    tbody.innerHTML = videosData.map(video => `
        <tr class="hover:bg-gray-50">
            <td class="px-6 py-4">
                <div class="flex items-start">
                    <img class="h-10 w-16 object-cover rounded flex-shrink-0" src="${video.thumbnail}" alt="${video.title}">
                    <div class="ml-4 min-w-0 flex-1">
                        <div class="text-sm font-medium text-gray-900 leading-tight line-clamp-2">${video.title}</div>
                    </div>
                </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${formatNumber(video.views)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${formatNumber(video.likes)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${video.length}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${video.watchTime}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm ${getWatchPercentageColor(video.percentWatched, video.length)}">${video.percentWatched}%</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${formatNumber(video.subsGained)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${formatDate(video.publishedAt)}</td>
        </tr>
    `).join('');
}

// Initialize dashboard
document.addEventListener('DOMContentLoaded', async function() {
    // Initialize refresh button status timer
    updateRefreshButtonStatus();
    setInterval(updateRefreshButtonStatus, 1000); // Update every second
    
    // First check if user is authenticated
    try {
        const response = await fetch('/api/channel');
        const data = await response.json();
        
        if (data.authenticated) {
            // Track authenticated user visit
            if (typeof gtag !== 'undefined') {
                gtag('event', 'user_visit', {
                    'event_category': 'engagement',
                    'event_label': 'authenticated_user',
                    'custom_parameter_1': 'signed_in'
                });
            }
            
            // Track successful sign-in only if user just completed OAuth
            const urlParams = new URLSearchParams(window.location.search);
            const justSignedIn = urlParams.get('just_signed_in');
            
            if (justSignedIn === 'true') {
                console.log('🔍 User just completed OAuth, checking gtag availability:', typeof gtag);
                if (typeof gtag !== 'undefined') {
                    console.log('✅ Sending sign_in_success event for completed OAuth');
                    gtag('event', 'sign_in_success', {
                        'event_category': 'engagement',
                        'event_label': 'successful_authentication'
                    });
                } else {
                    console.log('❌ gtag not available for sign_in_success');
                }
                
                // Clean up the URL parameter
                const newUrl = window.location.pathname;
                window.history.replaceState({}, document.title, newUrl);
            }
            
            // User is authenticated - show channel info and load videos
            const channelInfo = document.getElementById('channel-info');
            channelInfo.innerHTML = `
                <div class="flex items-center space-x-2">
                    <img class="w-8 h-8 rounded-full" src="${data.thumbnail}" alt="${data.title}">
                    <div class="font-medium">${data.title}</div>
                </div>
            `;
            
            // Show logout button for authenticated users
            const logoutBtn = document.getElementById('logout-btn');
            if (logoutBtn) {
                logoutBtn.style.display = 'block';
            }
            
            loadVideos();
        } else {
            // Track unauthenticated user visit
            if (typeof gtag !== 'undefined') {
                gtag('event', 'user_visit', {
                    'event_category': 'engagement',
                    'event_label': 'unauthenticated_user',
                    'custom_parameter_1': 'signed_out'
                });
            }
            
            // User is not authenticated - show sign in button and placeholder
            const channelInfo = document.getElementById('channel-info');
            channelInfo.innerHTML = `
                <a href="/auth/google" class="text-white hover:text-blue-200 transition-colors text-sm flex items-center" onclick="console.log('🔍 Header sign-in clicked, gtag available:', typeof gtag); if(typeof gtag !== 'undefined') { console.log('✅ Sending header sign_in_click event'); gtag('event', 'sign_in_click', { 'event_category': 'engagement', 'event_label': 'header_button' }); } else { console.log('❌ gtag not available for header sign-in'); } return true;">
                    <i class="fas fa-sign-in-alt mr-1"></i>
                    Sign In
                </a>
            `;
            
            // Hide logout button for unauthenticated users
            const logoutBtn = document.getElementById('logout-btn');
            if (logoutBtn) {
                logoutBtn.style.display = 'none';
            }
            
            // Show sign-in placeholder in table area
            document.getElementById('videos-table').innerHTML = `
                <tr>
                    <td colspan="8" class="px-6 py-12 text-center">
                        <div class="flex flex-col items-center space-y-6">
                            <div class="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center">
                                <i class="fas fa-chart-line text-blue-600 text-2xl"></i>
                            </div>
                            <div class="text-center">
                                <h3 class="text-lg font-medium text-gray-900 mb-2">Sign in to view your YouTube analytics</h3>
                                <p class="text-gray-500 mb-6">Connect your Google account to see detailed metrics for your videos</p>
                                <a href="/auth/google" class="inline-flex items-center px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors" onclick="if(typeof gtag !== 'undefined') { gtag('event', 'sign_in_click', { 'event_category': 'engagement', 'event_label': 'dashboard_table_button' }); } return true;">
                                    <i class="fab fa-google mr-2"></i>
                                    Sign in with Google
                                </a>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
            
            // Update video count to show sign in message
            const countElement = document.getElementById('video-count');
            if (countElement) {
                countElement.textContent = 'Sign in to view your videos';
                countElement.className = 'text-sm text-gray-500';
            }
        }
    } catch (error) {
        console.error('Error checking authentication status:', error);
        // Fallback - load both
        loadChannelInfo();
        loadVideos();
    }
});