#!/bin/bash

echo "🔄 Updating yt-dlp to latest version..."

# Navigate to backend directory
cd backend

# Activate virtual environment and update yt-dlp
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install -U yt-dlp
    echo "✅ yt-dlp updated successfully!"
    echo ""
    echo "Current version:"
    yt-dlp --version
else
    echo "❌ Virtual environment not found!"
    echo "Please run this script from the project root directory"
    exit 1
fi
