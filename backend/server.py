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

class VideoInfo(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    duration: Optional[int] = None
    source: str
    formats: List[VideoFormat]

class DownloadRequest(BaseModel):
    url: str
    format_id: str

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


def download_video(url: str, format_id: str, task_id: str, output_path: str):
    """Download video using yt-dlp with ffmpeg merging"""
    download_progress[task_id] = {
        'progress': 0,
        'status': 'starting',
        'speed': None,
        'eta': None
    }
    
    ydl_opts = {
        'format': format_id,
        'outtmpl': output_path,
        'progress_hooks': [lambda d: progress_hook(d, task_id)],
        'merge_output_format': 'mp4',
        'postprocessor_args': [
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-strict', 'experimental'
        ],
        'prefer_ffmpeg': True,
        'quiet': False,
    }
    
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
        
        # Parse formats and filter for best quality video+audio combinations
        formats_list = []
        seen_qualities = set()
        
        # Get formats with both video and audio, or best separate streams
        for fmt in info.get('formats', []):
            format_id = fmt.get('format_id')
            height = fmt.get('height')
            fps = fmt.get('fps')
            vcodec = fmt.get('vcodec', 'none')
            acodec = fmt.get('acodec', 'none')
            filesize = fmt.get('filesize')
            ext = fmt.get('ext', 'mp4')
            
            # Skip formats without video
            if not height or vcodec == 'none':
                continue
            
            # Create quality label
            quality = f"{height}p"
            if fps and fps > 30:
                quality += f" {fps}fps"
            
            # Avoid duplicates
            if quality in seen_qualities:
                continue
            
            seen_qualities.add(quality)
            
            formats_list.append(VideoFormat(
                format_id=format_id,
                quality=quality,
                resolution=f"{fmt.get('width', 0)}x{height}",
                fps=fps,
                filesize=format_filesize(filesize) if filesize else "Unknown",
                ext=ext,
                vcodec=vcodec,
                acodec=acodec if acodec != 'none' else None
            ))
        
        # Sort by resolution (descending)
        formats_list.sort(
            key=lambda x: int(x.quality.split('p')[0]) if 'p' in x.quality else 0,
            reverse=True
        )
        
        # Return top 10 formats
        return VideoInfo(
            title=info.get('title', 'Unknown'),
            thumbnail=info.get('thumbnail'),
            duration=info.get('duration'),
            source=source,
            formats=formats_list[:10]
        )
        
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to analyze video: {str(e)}")


@api_router.post("/download")
async def download_video_endpoint(request: DownloadRequest):
    """Download video and stream it back"""
    task_id = str(uuid.uuid4())
    
    try:
        # Create temporary directory for this download
        temp_dir = tempfile.mkdtemp()
        output_template = os.path.join(temp_dir, 'video.%(ext)s')
        
        # Start download in thread pool
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            executor,
            download_video,
            request.url,
            request.format_id,
            task_id,
            output_template
        )
        
        if not success:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Download failed")
        
        # Find the downloaded file
        files = list(Path(temp_dir).glob('video.*'))
        if not files:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Downloaded file not found")
        
        video_file = files[0]
        
        def file_iterator():
            try:
                with open(video_file, 'rb') as f:
                    while chunk := f.read(8192):
                        yield chunk
            finally:
                # Cleanup after streaming
                shutil.rmtree(temp_dir, ignore_errors=True)
                if task_id in download_progress:
                    del download_progress[task_id]
        
        return StreamingResponse(
            file_iterator(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename=video.mp4"
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