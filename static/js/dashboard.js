let videosData = [];
let currentSort = { column: 'published', direction: 'desc' };
let currentPage = 1;
let perPage = 10;
let paginationData = null;

// Format numbers with commas
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

// Format duration from seconds
function formatDuration(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

// Get watch percentage color based on video length
function getWatchPercentageColor(watchPercent, videoLength) {
    const lengthInSeconds = parseInt(videoLength);
    
    // Define benchmarks based on video length
    let goodRange, excellentRange;
    
    if (lengthInSeconds <= 15) {
        goodRange = [85, 100];
        excellentRange = [95, 100];
    } else if (lengthInSeconds <= 30) {
        goodRange = [75, 90];
        excellentRange = [85, 100];
    } else if (lengthInSeconds <= 45) {
        goodRange = [70, 85];
        excellentRange = [80, 100];
    } else if (lengthInSeconds <= 60) {
        goodRange = [65, 80];
        excellentRange = [75, 100];
    } else {
        // For videos longer than 60 seconds, use a general benchmark
        goodRange = [60, 75];
        excellentRange = [70, 100];
    }
    
    if (watchPercent >= excellentRange[0]) {
        return 'text-blue-600 font-bold'; // Blue for excellent
    } else if (watchPercent >= goodRange[0]) {
        return 'text-green-600 font-semibold'; // Green for good
    } else {
        return 'text-orange-600 font-semibold'; // Orange for below target
    }
}

// Load channel information
async function loadChannelInfo() {
    try {
        const response = await fetch('/api/channel');
        const data = await response.json();
        
        const channelInfo = document.getElementById('channel-info');
        
        if (response.ok && !data.error) {
            // Success - show channel info
            channelInfo.innerHTML = `
                <div class="flex items-center space-x-2">
                    <img class="w-8 h-8 rounded-full" src="${data.thumbnail}" alt="${data.title}">
                    <div>
                        <div class="font-medium">${data.title}</div>
                        <div class="text-xs opacity-75">${formatNumber(data.subscriberCount)} subscribers</div>
                    </div>
                </div>
            `;
        } else {
            // Error or authentication required - show sign-in button
            channelInfo.innerHTML = `
                <div class="flex items-center space-x-2">
                    <div class="text-sm opacity-75">${data.title || 'YouTube Dashboard'}</div>
                    <button onclick="signIn()" class="px-3 py-1 text-xs bg-white bg-opacity-20 rounded hover:bg-opacity-30 transition-colors">
                        Sign In
                    </button>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading channel info:', error);
        const channelInfo = document.getElementById('channel-info');
        channelInfo.innerHTML = `
            <div class="flex items-center space-x-2">
                <div class="text-sm opacity-75">YouTube Dashboard</div>
                <button onclick="signIn()" class="px-3 py-1 text-xs bg-white bg-opacity-20 rounded hover:bg-opacity-30 transition-colors">
                    Sign In
                </button>
            </div>
        `;
    }
}

// Sign in function (placeholder for now)
function signIn() {
    alert('Sign-in feature coming soon! For now, this dashboard is configured for a single user.');
}

// Load videos data
async function loadVideos(forceRefresh = false) {
    try {
        const url = `/api/videos?sort_by=${currentSort.column}&sort_direction=${currentSort.direction}&page=${currentPage}&per_page=${perPage}&refresh=${forceRefresh}`;
        const response = await fetch(url);
        const data = await response.json();
        
        // Handle new data structure with last_updated
        if (data.videos && data.last_updated) {
            videosData = data.videos;
            paginationData = data.pagination; // Assuming pagination data is returned
            // Update the last updated timestamp in the header
            document.getElementById('last-updated').textContent = `Last Updated: ${data.last_updated}`;
        } else {
            // Fallback for old data structure
            videosData = data;
            paginationData = null; // No pagination data if old structure
        }
        
        updateTable();
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
                aVal = new Date(a.published);
                bVal = new Date(b.published);
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
                aVal = parseInt(a.video_length);
                bVal = parseInt(b.video_length);
                break;
            case 'watchTime':
                aVal = a.avg_duration;
                bVal = b.avg_duration;
                break;
            case 'watched':
                aVal = a.avg_view_percent;
                bVal = b.avg_view_percent;
                break;
            case 'subs':
                aVal = a.subs_gained;
                bVal = b.subs_gained;
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
    
    // Reset to first page when sorting
    currentPage = 1;
    
    // Load videos with new sort
    loadVideos();
}

// Update pagination controls
function updatePagination() {
    const controls = document.getElementById('pagination-controls');
    
    if (!paginationData) {
        controls.classList.add('hidden');
        return;
    }
    
    controls.classList.remove('hidden');
    
    // Update pagination info
    document.getElementById('showing-start').textContent = ((paginationData.current_page - 1) * paginationData.per_page) + 1;
    document.getElementById('showing-end').textContent = Math.min(paginationData.current_page * paginationData.per_page, paginationData.total_videos);
    document.getElementById('total-videos').textContent = paginationData.total_videos;
    document.getElementById('page-info').textContent = `Page ${paginationData.current_page} of ${paginationData.total_pages}`;
    
    // Update button states
    document.getElementById('prev-page').disabled = !paginationData.has_prev;
    document.getElementById('next-page').disabled = !paginationData.has_next;
}

// Pagination event handlers
function goToPage(page) {
    currentPage = page;
    loadVideos();
}

function nextPage() {
    if (paginationData && paginationData.has_next) {
        goToPage(currentPage + 1);
    }
}

function prevPage() {
    if (paginationData && paginationData.has_prev) {
        goToPage(currentPage - 1);
    }
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

// Update videos table with pagination
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
    
    // Display current page videos
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
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${video.published}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${formatNumber(video.views)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${formatNumber(video.likes)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${video.video_length}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${formatDuration(video.avg_duration)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm ${getWatchPercentageColor(video.avg_view_percent, video.video_length)}">${video.avg_view_percent.toFixed(1)}%</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${formatNumber(video.subs_gained)}</td>
        </tr>
    `).join('');
    
    // Update pagination controls
    updatePagination();
}

// Initialize dashboard
document.addEventListener('DOMContentLoaded', function() {
    loadChannelInfo();
    loadVideos();
    
    // Add event listeners for pagination
    document.getElementById('prev-page').addEventListener('click', prevPage);
    document.getElementById('next-page').addEventListener('click', nextPage);
});