let currentImage = null;
let frameCount = 921;
let frameElement = document.getElementById('frame-count');
let mainFeed = document.getElementById('main-feed');
let cornerFeeds = document.querySelectorAll('.corner-feed');

function updateFrame() {
    frameCount++;
    frameElement.innerText = String(frameCount).padStart(5, '0');
}

setInterval(updateFrame, 100);

async function fetchLatestImage() {
    try {
        const response = await fetch('/api/latest-image');
        const data = await response.json();
        
        if (data.latest && data.latest !== currentImage) {
            currentImage = data.latest;
            const imgUrl = `/api/image/${currentImage}`;
            
            // Wait for image to load before swapping
            const img = new Image();
            img.onload = () => {
                // Update main feed
                mainFeed.src = imgUrl;
                
                // Update corner bubbles
                cornerFeeds.forEach(feed => {
                    feed.src = imgUrl;
                });
            };
            img.src = imgUrl;
        }
    } catch (error) {
        console.error('Error fetching image:', error);
    }
}

// Initial fetch
fetchLatestImage();

// Poll every 1 second
setInterval(fetchLatestImage, 1000);

// Controls Logic
let currentZoom = 1;
let currentMode = 'default';

const btnZoomIn = document.getElementById('btn-zoom-in');
const btnZoomOut = document.getElementById('btn-zoom-out');
const btnThermal = document.getElementById('btn-thermal');
const btnNight = document.getElementById('btn-night');

btnZoomIn.addEventListener('click', (e) => {
    e.preventDefault();
    currentZoom += 0.2;
    if (currentZoom > 3) currentZoom = 3;
    updateFilters();
});

btnZoomOut.addEventListener('click', (e) => {
    e.preventDefault();
    currentZoom -= 0.2;
    if (currentZoom < 1) currentZoom = 1;
    updateFilters();
});

btnThermal.addEventListener('click', (e) => {
    e.preventDefault();
    currentMode = currentMode === 'thermal' ? 'default' : 'thermal';
    updateFilters();
});

btnNight.addEventListener('click', (e) => {
    e.preventDefault();
    currentMode = currentMode === 'night' ? 'default' : 'night';
    updateFilters();
});

function updateFilters() {
    // Update active button state
    btnThermal.classList.remove('active');
    btnNight.classList.remove('active');
    
    let filterString = '';
    if (currentMode === 'default') {
        filterString = 'sepia(100%) hue-rotate(270deg) saturate(800%) contrast(300%) invert(10%)';
    } else if (currentMode === 'thermal') {
        btnThermal.classList.add('active');
        // Red, orange, blue heat-map style filter
        filterString = 'invert(100%) sepia(100%) saturate(1000%) hue-rotate(300deg) contrast(200%) brightness(150%)';
    } else if (currentMode === 'night') {
        btnNight.classList.add('active');
        // Classic green night vision
        filterString = 'sepia(100%) hue-rotate(80deg) saturate(500%) contrast(200%) brightness(120%)';
    }

    mainFeed.style.transform = `scale(${currentZoom})`;
    mainFeed.style.filter = filterString;
}
