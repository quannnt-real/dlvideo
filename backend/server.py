from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import yt_dlp
import asyncio
import json
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=4)

# Global dict to track download progress
download_progress = {}


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class VideoAnalyzeRequest(BaseModel):
    url: str

class VideoFormat(BaseModel):
    format_id: str
    quality: str
    resolution: Optional[str] = None
    fps: Optional[int] = None
    filesize: Optional[str] = None
    ext: str
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    has_audio: bool = False
    has_video: bool = True
    format_note: Optional[str] = None

class VideoInfo(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    duration: Optional[int] = None
    source: str
    formats: List[VideoFormat]
    
    @classmethod
    def model_validate(cls, obj):
        # Convert float duration to int
        if 'duration' in obj and isinstance(obj['duration'], float):
            obj['duration'] = int(obj['duration'])
        return super().model_validate(obj)

class DownloadRequest(BaseModel):
    url: str
    format_id: str
    download_type: str = "video"  # "video" or "audio"

class ProgressResponse(BaseModel):
    progress: float
    status: str
    speed: Optional[str] = None
    eta: Optional[str] = None


def format_filesize(bytes_size):
    """Format filesize to human readable format"""
    if not bytes_size:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"


def extract_video_info(url: str) -> Dict[str, Any]:
    """Extract video information using yt-dlp"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info


def progress_hook(d, task_id):
    """Progress callback for yt-dlp"""
    if d['status'] == 'downloading':
        try:
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            
            if total > 0:
                progress = (downloaded / total) * 100
            else:
                progress = 0
            
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)
            
            download_progress[task_id] = {
                'progress': progress,
                'status': 'downloading',
                'speed': f"{speed / 1024 / 1024:.2f} MB/s" if speed else None,
                'eta': f"{eta}s" if eta else None
            }
        except Exception as e:
            logger.error(f"Progress hook error: {e}")
    elif d['status'] == 'finished':
        download_progress[task_id] = {
            'progress': 100,
            'status': 'processing',
            'speed': None,
            'eta': None
        }


def download_video(url: str, format_id: str, task_id: str, output_path: str, download_type: str = "video"):
    """Download video or audio using yt-dlp with smart merging"""
    download_progress[task_id] = {
        'progress': 0,
        'status': 'starting',
        'speed': None,
        'eta': None
    }
    
    # Base options
    ydl_opts = {
        'outtmpl': output_path,
        'progress_hooks': [lambda d: progress_hook(d, task_id)],
        'prefer_ffmpeg': True,
        'quiet': False,
    }
    
    if download_type == "audio":
        # Audio only download - convert to MP3
        ydl_opts.update({
            'format': format_id,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        # Video download with smart format selection
        # If format_id has audio, use it directly
        # Otherwise, let yt-dlp auto-merge best video+audio
        if '+' in format_id:
            # Manual format combination (e.g., "137+140")
            ydl_opts['format'] = format_id
        else:
            # Single format - check if it needs audio
            # Use bestvideo+bestaudio merge if format doesn't have audio
            ydl_opts['format'] = f"{format_id}+bestaudio/best"
        
        ydl_opts['merge_output_format'] = 'mp4'
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        download_progress[task_id] = {
            'progress': 100,
            'status': 'completed',
            'speed': None,
            'eta': None
        }
        return True
    except Exception as e:
        download_progress[task_id] = {
            'progress': 0,
            'status': f'error: {str(e)}',
            'speed': None,
            'eta': None
        }
        logger.error(f"Download error: {e}")
        return False


# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Video Downloader API"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks


@api_router.post("/analyze", response_model=VideoInfo)
async def analyze_video(request: VideoAnalyzeRequest):
    """Analyze video URL and return available formats"""
    try:
        # Run blocking operation in thread pool
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(executor, extract_video_info, request.url)
        
        # Extract source platform
        source = info.get('extractor_key', 'Unknown')
        
        # Parse formats and prioritize formats with both video+audio
        formats_list = []
        audio_formats = []
        seen_qualities = set()
        
        # Separate video and audio formats
        for fmt in info.get('formats', []):
            format_id = fmt.get('format_id')
            height = fmt.get('height')
            fps = fmt.get('fps')
            vcodec = fmt.get('vcodec', 'none')
            acodec = fmt.get('acodec', 'none')
            filesize = fmt.get('filesize')
            ext = fmt.get('ext', 'mp4')
            format_note = fmt.get('format_note', '')
            abr = fmt.get('abr', 0)  # Audio bitrate
            
            has_video = bool(vcodec != 'none' and height)
            has_audio = bool(acodec != 'none')
            
            # Audio only formats
            if not has_video and has_audio:
                audio_formats.append({
                    'format_id': format_id,
                    'quality': f"{int(abr)}kbps" if abr else "Audio",
                    'ext': ext,
                    'acodec': acodec,
                    'filesize': filesize,
                    'abr': abr or 0
                })
                continue
            
            # Skip formats without video
            if not has_video:
                continue
            
            # Create quality label
            quality = f"{height}p"
            if fps and fps > 30:
                quality += f" {fps}fps"
            
            # Add audio indicator
            audio_indicator = " (có âm thanh)" if has_audio else " (không có âm thanh)"
            quality_display = quality + audio_indicator
            
            # Prefer formats with audio - use different quality key
            quality_key = f"{height}_{has_audio}"
            if quality_key in seen_qualities:
                continue
            
            seen_qualities.add(quality_key)
            
            formats_list.append(VideoFormat(
                format_id=format_id,
                quality=quality_display,
                resolution=f"{fmt.get('width', 0)}x{height}",
                fps=fps,
                filesize=format_filesize(filesize) if filesize else "Unknown",
                ext=ext,
                vcodec=vcodec,
                acodec=acodec if acodec != 'none' else None,
                has_audio=has_audio,
                has_video=has_video,
                format_note=format_note
            ))
        
        # Sort: prioritize formats WITH audio, then by resolution
        formats_list.sort(
            key=lambda x: (
                x.has_audio,  # Formats with audio first
                int(x.quality.split('p')[0]) if 'p' in x.quality else 0  # Then by resolution
            ),
            reverse=True
        )
        
        # Add best audio formats
        audio_formats.sort(key=lambda x: x['abr'], reverse=True)
        for audio_fmt in audio_formats[:3]:  # Top 3 audio qualities
            formats_list.append(VideoFormat(
                format_id=audio_fmt['format_id'],
                quality=f"MP3 - {audio_fmt['quality']}",
                resolution=None,
                fps=None,
                filesize=format_filesize(audio_fmt['filesize']) if audio_fmt['filesize'] else "Unknown",
                ext='mp3',
                vcodec=None,
                acodec=audio_fmt['acodec'],
                has_audio=True,
                has_video=False,
                format_note="Audio only"
            ))
        
        # Convert duration to int if float
        duration = info.get('duration')
        if duration and isinstance(duration, float):
            duration = int(duration)
        
        # Return top 10 formats
        return VideoInfo(
            title=info.get('title', 'Unknown'),
            thumbnail=info.get('thumbnail'),
            duration=duration,
            source=source,
            formats=formats_list[:10]
        )
        
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to analyze video: {str(e)}")


@api_router.post("/download")
async def download_video_endpoint(request: DownloadRequest):
    """Download video or audio and stream it back"""
    task_id = str(uuid.uuid4())
    
    try:
        # Create temporary directory for this download
        temp_dir = tempfile.mkdtemp()
        output_template = os.path.join(temp_dir, 'download.%(ext)s')
        
        # Start download in thread pool
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            executor,
            download_video,
            request.url,
            request.format_id,
            task_id,
            output_template,
            request.download_type
        )
        
        if not success:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Download failed")
        
        # Find the downloaded file
        files = list(Path(temp_dir).glob('download.*'))
        if not files:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Downloaded file not found")
        
        downloaded_file = files[0]
        file_ext = downloaded_file.suffix
        
        # Determine media type and filename
        if request.download_type == "audio" or file_ext == '.mp3':
            media_type = "audio/mpeg"
            filename = "audio.mp3"
        else:
            media_type = "video/mp4"
            filename = "video.mp4"
        
        def file_iterator():
            try:
                with open(downloaded_file, 'rb') as f:
                    while chunk := f.read(8192):
                        yield chunk
            finally:
                # Cleanup after streaming
                shutil.rmtree(temp_dir, ignore_errors=True)
                if task_id in download_progress:
                    del download_progress[task_id]
        
        return StreamingResponse(
            file_iterator(),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@api_router.get("/progress/{task_id}", response_model=ProgressResponse)
async def get_progress(task_id: str):
    """Get download progress for a task"""
    if task_id not in download_progress:
        raise HTTPException(status_code=404, detail="Task not found")
    
    progress_data = download_progress[task_id]
    return ProgressResponse(**progress_data)


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
    executor.shutdown(wait=False)