const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3000;

app.use(cors());

// Serve static frontend files
app.use(express.static(path.join(__dirname, 'public')));

// Path to the images folder
const IMAGES_DIR = path.join(__dirname, '..', 'images');

// Serve the raw images at /api/image/...
app.use('/api/image', express.static(IMAGES_DIR));

// Endpoint to get the name of the latest image in the folder
app.get('/api/latest-image', (req, res) => {
    try {
        if (!fs.existsSync(IMAGES_DIR)) {
            return res.json({ latest: null });
        }

        const files = fs.readdirSync(IMAGES_DIR);
        // Filter for files starting with 'intruder_' and ending with '.jpg'
        const imageFiles = files.filter(f => f.startsWith('intruder_') && f.endsWith('.jpg'));

        if (imageFiles.length === 0) {
            return res.json({ latest: null });
        }

        // Sort files by timestamp extracted from the filename `intruder_{timestamp}.jpg`
        imageFiles.sort((a, b) => {
            const timeA = parseInt(a.replace('intruder_', '').replace('.jpg', ''), 10);
            const timeB = parseInt(b.replace('intruder_', '').replace('.jpg', ''), 10);
            return timeB - timeA; // Descending order
        });

        res.json({ latest: imageFiles[0] });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Server error' });
    }
});

app.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT}`);
});
