from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, UploadFile, File
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

# Import authentication modules
from auth_middleware import AuthMiddleware
from auth_routes import auth_router

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection (optional)
try:
    mongo_url = os.environ.get('MONGO_URL')
    if mongo_url and not os.environ.get('DISABLE_MONGO'):
        client = AsyncIOMotorClient(mongo_url)
        db = client[os.environ['DB_NAME']]
    else:
        client = None
        db = None
except Exception as e:
    print(f"MongoDB connection failed: {e}")
    client = None
    db = None

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=4)

# Global dict to track download progress and file storage
download_progress = {}
# Store task files with their paths and metadata
task_files = {}  # task_id -> {file_path, temp_dir, ready, created_at}

# Create downloads directory for serving files
DOWNLOADS_DIR = ROOT_DIR / 'downloads'
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Create uploads directory for audio editor
UPLOADS_DIR = ROOT_DIR / 'uploads'
UPLOADS_DIR.mkdir(exist_ok=True)

# Global dict to track audio processing tasks
audio_tasks = {}  # task_id -> {audio_id, file_path, status, progress, ready, created_at}

# Global dict to track uploaded audio files with original filenames
uploaded_audio_files = {}  # audio_id -> original_filename


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

class AudioOptions(BaseModel):
    codec: str = "mp3"              # mp3, m4a, opus, copy
    qscale: Optional[int] = None    # 0-9 for VBR (None = not used)
    bitrate: str = "192k"           # CBR bitrate
    channels: str = "stereo"        # mono, stereo
    volume: int = 100               # 0-200% (100 = original)
    sampleRate: str = "44100"       # Hz
    trimStart: str = ""             # HH:MM:SS
    trimEnd: str = ""               # HH:MM:SS
    # Fade options
    enableFadeIn: bool = False      # Enable fade in at start
    fadeInDuration: float = 3.0     # Fade in duration in seconds
    enableFadeOut: bool = False     # Enable fade out at end
    fadeOutDuration: float = 3.0    # Fade out duration in seconds
    # Cut middle section
    enableCutMiddle: bool = False   # Enable cutting middle section
    cutMiddleStart: str = ""        # HH:MM:SS - start of section to cut
    cutMiddleEnd: str = ""          # HH:MM:SS - end of section to cut
    enableCrossfade: bool = False   # Enable crossfade when joining
    crossfadeDuration: float = 2.0  # Crossfade duration in seconds

class DownloadRequest(BaseModel):
    url: str
    format_id: str
    download_type: str = "video"  # "video" or "audio"
    audio_options: Optional[AudioOptions] = None

class ProgressResponse(BaseModel):
    progress: float
    status: str
    message: Optional[str] = None
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
    logger.info(f"=== Extracting video info for URL: {url}")
    
    ydl_opts = {
        'quiet': False,  # Enable output for debugging
        'no_warnings': False,  # Show warnings
        'extract_flat': False,
        'verbose': True,  # Enable verbose logging
        # Add headers to bypass 403 errors
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'nocheckcertificate': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            logger.info(f"=== Successfully extracted info for: {info.get('title', 'Unknown')}")
            logger.info(f"=== Extractor: {info.get('extractor', 'Unknown')}")
            logger.info(f"=== Available formats count: {len(info.get('formats', []))}")
            return info
    except Exception as e:
        logger.error(f"=== Error extracting video info: {e}")
        raise


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


def validate_format_availability(url: str, format_id: str) -> bool:
    """Validate if format is available before download"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            available_formats = info.get('formats', [])
            
            # Handle merged formats (e.g., "313+251")
            if '+' in format_id:
                format_parts = format_id.split('+')
                for part in format_parts:
                    if not any(f.get('format_id') == part for f in available_formats):
                        logger.warning(f"⚠️ Format part {part} not available")
                        return False
                return True
            else:
                # Single format
                return any(f.get('format_id') == format_id for f in available_formats)
    except Exception as e:
        logger.error(f"❌ Format validation error: {e}")
        return False


def get_format_info(url: str, format_id: str):
    """Get format information to determine best merge strategy"""
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            # Find the requested format
            fmt = next((f for f in formats if f.get('format_id') == format_id), None)
            if fmt:
                return {
                    'ext': fmt.get('ext'),
                    'vcodec': fmt.get('vcodec'),
                    'acodec': fmt.get('acodec'),
                    'height': fmt.get('height'),
                }
    except Exception as e:
        logger.warning(f"⚠️ Could not get format info: {e}")
    return None


def process_audio_with_ffmpeg(input_file: str, output_file: str, audio_options: dict, task_id: str):
    """
    Process audio file with FFmpeg based on user options
    Supports: trim, fade in/out, cut middle section with crossfade
    Returns: True if successful, False otherwise
    """
    import subprocess
    import json

    logger.info(f"🎵 Processing audio with options: {audio_options}")

    try:
        # First, get audio duration using ffprobe (needed for fade out calculation)
        # We need the ORIGINAL duration, then calculate the trimmed duration
        original_audio_duration = None
        try:
            probe_cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', input_file
            ]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            if probe_result.returncode == 0:
                probe_data = json.loads(probe_result.stdout)
                duration_str = probe_data.get('format', {}).get('duration')
                if duration_str:
                    original_audio_duration = float(duration_str)
                    logger.info(f"📊 Original audio duration: {original_audio_duration:.2f}s")
        except Exception as e:
            logger.warning(f"⚠️ Could not get audio duration: {e}")

        cmd = ['ffmpeg', '-y', '-i', input_file]

        # Build audio filter chain
        audio_filters = []

        # Check if we need to use filter_complex (for cut middle)
        use_filter_complex = audio_options.get('enableCutMiddle', False)

        if use_filter_complex:
            # Cut middle section and join segments
            cut_start = audio_options.get('cutMiddleStart', '')
            cut_end = audio_options.get('cutMiddleEnd', '')
            enable_crossfade = audio_options.get('enableCrossfade', False)
            crossfade_duration = audio_options.get('crossfadeDuration', 2.0)

            if cut_start and cut_end:
                logger.info(f"✂️ Cutting middle section from {cut_start} to {cut_end}")

                # Build filter_complex
                # [0:a] - input audio stream
                # atrim to get first segment (0 to cut_start)
                # atrim to get second segment (cut_end to end)
                filter_complex = f"[0:a]atrim=end={cut_start},asetpts=PTS-STARTPTS"

                # Add fade out to first segment if enabled
                if enable_crossfade:
                    filter_complex += f",afade=t=out:st={cut_start}:d={crossfade_duration}"

                filter_complex += "[a1];"

                filter_complex += f"[0:a]atrim=start={cut_end},asetpts=PTS-STARTPTS"

                # Add fade in to second segment if enabled
                if enable_crossfade:
                    filter_complex += f",afade=t=in:st=0:d={crossfade_duration}"

                filter_complex += "[a2];"

                # Concatenate or crossfade
                if enable_crossfade:
                    filter_complex += f"[a1][a2]acrossfade=d={crossfade_duration}[aout]"
                    logger.info(f"🔀 Using crossfade: {crossfade_duration}s")
                else:
                    filter_complex += "[a1][a2]concat=n=2:v=0:a=1[aout]"

                cmd.extend(['-filter_complex', filter_complex])
                cmd.extend(['-map', '[aout]'])

                logger.info(f"🔧 Filter complex: {filter_complex}")
            else:
                logger.warning("⚠️ Cut middle enabled but timestamps not provided, skipping")
                use_filter_complex = False

        if not use_filter_complex:
            # Standard trim
            trim_start = audio_options.get('trimStart', '').strip()
            trim_end = audio_options.get('trimEnd', '').strip()

            # Calculate effective audio duration AFTER trim
            def parse_timestamp(ts):
                """Convert HH:MM:SS to seconds"""
                if not ts or ts == '00:00:00':
                    return 0
                parts = ts.split(':')
                if len(parts) == 3:
                    h, m, s = parts
                    return int(h) * 3600 + int(m) * 60 + float(s)
                return 0

            trim_start_sec = parse_timestamp(trim_start)
            trim_end_sec = parse_timestamp(trim_end)

            # Check if fades are enabled
            enable_fade_in = audio_options.get('enableFadeIn', False)
            enable_fade_out = audio_options.get('enableFadeOut', False)
            has_trim = (trim_start and trim_start != '00:00:00') or (trim_end and trim_end != '00:00:00')

            # Calculate audio duration AFTER trim for fade calculation
            if trim_end_sec > 0:
                # Both trim start and end specified
                audio_duration = trim_end_sec - trim_start_sec
                logger.info(f"📊 Calculated trimmed duration: {audio_duration:.2f}s (from {trim_start} to {trim_end})")
            elif trim_start_sec > 0 and original_audio_duration:
                # Only trim start specified, trim to end
                audio_duration = original_audio_duration - trim_start_sec
                logger.info(f"📊 Calculated trimmed duration: {audio_duration:.2f}s (from {trim_start} to end)")
            else:
                # No trim or only trim end
                audio_duration = original_audio_duration
                if audio_duration:
                    logger.info(f"📊 Using original duration: {audio_duration:.2f}s")

            # When fades are enabled with trim, use atrim filter instead of -ss -to
            # This ensures PTS is properly reset for fade filters to work at correct positions
            if has_trim and (enable_fade_in or enable_fade_out):
                # Use atrim filter for accurate fade positioning
                atrim_filter = "atrim="
                if trim_start_sec > 0:
                    atrim_filter += f"start={trim_start_sec}"
                if trim_end_sec > 0:
                    if trim_start_sec > 0:
                        atrim_filter += ":"
                    atrim_filter += f"end={trim_end_sec}"

                audio_filters.append(atrim_filter)
                audio_filters.append("asetpts=PTS-STARTPTS")
                logger.info(f"✂️ Using atrim filter for accurate fade positioning: {atrim_filter}")
                logger.info(f"⏰ Resetting audio timestamps (PTS) for accurate fade positioning")
            else:
                # No fades or no trim: use command-line -ss -to for better performance
                if trim_start and trim_start != '00:00:00':
                    cmd.extend(['-ss', trim_start])
                    logger.info(f"✂️ Trim start: {trim_start}")
                if trim_end and trim_end != '00:00:00':
                    cmd.extend(['-to', trim_end])
                    logger.info(f"✂️ Trim end: {trim_end}")

            # Build audio filter for fade in/out and volume
            if enable_fade_in:
                fade_duration = audio_options.get('fadeInDuration', 3.0)
                audio_filters.append(f"afade=t=in:st=0:d={fade_duration}")
                logger.info(f"🎚️ Fade in: {fade_duration}s from start of trimmed audio")

            if enable_fade_out:
                fade_duration = audio_options.get('fadeOutDuration', 3.0)
                # Calculate fade out start time based on TRIMMED audio duration
                if audio_duration and audio_duration > fade_duration:
                    fade_start = audio_duration - fade_duration
                    audio_filters.append(f"afade=t=out:st={fade_start}:d={fade_duration}")
                    logger.info(f"🎚️ Fade out: {fade_duration}s (starting at {fade_start:.2f}s of trimmed audio)")
                else:
                    # Fallback: fade out entire audio if duration unknown or too short
                    audio_filters.append(f"afade=t=out:d={fade_duration}")
                    logger.info(f"🎚️ Fade out: {fade_duration}s (entire audio - duration too short or unknown)")

            # Volume adjustment
            volume = audio_options.get('volume', 100)
            if volume != 100:
                audio_filters.append(f"volume={volume/100}")
                logger.info(f"🔊 Volume: {volume}%")

            # Apply audio filters if any
            if audio_filters:
                cmd.extend(['-af', ','.join(audio_filters)])

        # Codec selection
        codec = audio_options.get('codec', 'mp3')
        if codec == 'copy':
            cmd.extend(['-c:a', 'copy'])
        else:
            # Set codec
            codec_map = {
                'mp3': 'libmp3lame',
                'm4a': 'aac',
                'opus': 'libopus',
                'flac': 'flac',
                'wav': 'pcm_s16le'  # WAV uses PCM
            }
            ffmpeg_codec = codec_map.get(codec, 'libmp3lame')
            cmd.extend(['-c:a', ffmpeg_codec])

            # Quality/Bitrate settings (only for lossy formats)
            if codec not in ['flac', 'wav']:
                qscale = audio_options.get('qscale')
                if qscale is not None and codec == 'mp3':
                    cmd.extend(['-q:a', str(qscale)])
                    logger.info(f"  VBR qscale: {qscale}")
                else:
                    bitrate = audio_options.get('bitrate', '192k')
                    cmd.extend(['-b:a', bitrate])
                    logger.info(f"  CBR bitrate: {bitrate}")

            # Channels (mono/stereo)
            channels = audio_options.get('channels', 'stereo')
            if channels == 'mono':
                cmd.extend(['-ac', '1'])
            elif channels == 'stereo':
                cmd.extend(['-ac', '2'])

            # Sample Rate
            sample_rate = audio_options.get('sampleRate', '44100')
            cmd.extend(['-ar', sample_rate])

        # Output file
        cmd.append(output_file)

        logger.info(f"🔧 FFmpeg command: {' '.join(cmd)}")

        # Run FFmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        if result.returncode != 0:
            logger.error(f"❌ FFmpeg failed: {result.stderr}")
            return False

        logger.info(f"✅ Audio processing completed: {output_file}")
        return True

    except subprocess.TimeoutExpired:
        logger.error(f"❌ FFmpeg timeout after 10 minutes")
        return False
    except Exception as e:
        logger.error(f"❌ Audio processing error: {e}")
        return False


def check_and_reencode_av1(file_path: str, task_id: str = None) -> bool:
    """
    Check if video uses AV1 codec and re-encode to H.264 if needed.
    Returns True if re-encoding was done, False otherwise.
    """
    import subprocess
    import json

    if not os.path.exists(file_path):
        logger.warning(f"⚠️ File not found for AV1 check: {file_path}")
        return False

    try:
        # Use ffprobe to check video codec and duration
        probe_cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_streams', '-show_format', file_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            logger.warning(f"⚠️ ffprobe failed for {file_path}")
            return False

        probe_data = json.loads(result.stdout)
        streams = probe_data.get('streams', [])

        if not streams:
            logger.warning(f"⚠️ No video stream found in {file_path}")
            return False

        # Find video stream
        video_stream = None
        for stream in streams:
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break

        if not video_stream:
            logger.warning(f"⚠️ No video stream found in {file_path}")
            return False

        video_codec = video_stream.get('codec_name', '')
        logger.info(f"🔍 Detected video codec: {video_codec}")

        # Check if it's AV1
        if video_codec not in ['av1', 'av01']:
            logger.info(f"✅ Video codec {video_codec} is compatible, no re-encoding needed")
            return False

        # Get video duration
        duration = None
        format_info = probe_data.get('format', {})
        if 'duration' in format_info:
            try:
                duration = float(format_info['duration'])
                logger.info(f"⏱️ Video duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
            except:
                pass

        # AV1 detected - need to re-encode
        logger.warning(f"⚠️ AV1 codec detected! Re-encoding to H.264 for better compatibility...")

        # Calculate timeout based on video duration (rough estimate: 2x duration, min 10 min, max 60 min)
        if duration:
            timeout = max(600, min(int(duration * 2), 3600))
            logger.info(f"⏳ Estimated re-encoding timeout: {timeout} seconds ({timeout/60:.1f} minutes)")
        else:
            timeout = 1800  # Default 30 minutes if duration unknown
            logger.info(f"⏳ Using default timeout: {timeout} seconds (duration unknown)")

        if task_id:
            download_progress[task_id] = {
                'progress': 80,
                'status': 'processing',
                'message': 'Đang chuyển đổi AV1 sang H.264 để tương thích... (có thể mất vài phút)',
                'speed': None,
                'eta': None
            }

        # Create temp output file
        temp_output = file_path.replace('.mp4', '_h264.mp4')

        # Re-encode with H.264
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', file_path,
            '-c:v', 'libx264',      # Use H.264 codec
            '-preset', 'fast',       # Fast encoding
            '-crf', '23',            # Good quality
            '-c:a', 'copy',          # Copy audio (already AAC)
            '-movflags', '+faststart',
            temp_output
        ]

        logger.info(f"🔄 Re-encoding command: {' '.join(ffmpeg_cmd)}")
        logger.info(f"🚀 Starting re-encoding process...")

        encode_result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if encode_result.returncode != 0:
            logger.error(f"❌ Re-encoding failed with return code {encode_result.returncode}")
            logger.error(f"❌ FFmpeg stderr: {encode_result.stderr[:500]}")
            # Clean up temp file if exists
            if os.path.exists(temp_output):
                os.remove(temp_output)
            return False

        # Check if output file was created successfully
        if not os.path.exists(temp_output):
            logger.error(f"❌ Re-encoded file not found: {temp_output}")
            return False

        # Replace original file with re-encoded version
        original_size = os.path.getsize(file_path) / (1024*1024)
        new_size = os.path.getsize(temp_output) / (1024*1024)

        os.remove(file_path)
        os.rename(temp_output, file_path)

        logger.info(f"✅ Re-encoding successful!")
        logger.info(f"📊 Original (AV1): {original_size:.2f} MB → H.264: {new_size:.2f} MB")

        return True

    except subprocess.TimeoutExpired:
        logger.error(f"❌ Re-encoding timeout after {timeout} seconds")
        logger.error(f"⚠️ Video may be too long or encoding is too slow")
        # Clean up temp file if exists
        temp_output = file_path.replace('.mp4', '_h264.mp4')
        if os.path.exists(temp_output):
            logger.info(f"🗑️ Cleaning up incomplete temp file: {temp_output}")
            os.remove(temp_output)
        return False
    except Exception as e:
        logger.error(f"❌ Error checking/re-encoding AV1: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def download_and_merge_local(url: str, video_format: str, audio_format: str, task_id: str, output_path: str):
    """Download video and audio separately, then merge locally with FFmpeg and convert to MP4"""
    import subprocess
    import os

    temp_dir = os.path.dirname(output_path)
    # Use generic extensions - let yt-dlp decide the actual format
    video_file = os.path.join(temp_dir, 'video_temp')
    audio_file = os.path.join(temp_dir, 'audio_temp')
    
    logger.info(f"🎬 LOCAL MERGE STRATEGY")
    logger.info(f"📹 Video format: {video_format}")
    logger.info(f"🔊 Audio format: {audio_format}")
    
    try:
        # Download video only (yt-dlp will add proper extension)
        logger.info("⬇️ Step 1/3: Downloading video stream...")
        download_progress[task_id] = {
            'progress': 10,
            'status': 'downloading',
            'message': 'Đang tải video stream...',
            'speed': None,
            'eta': None
        }
        
        video_opts = {
            'format': video_format,
            'outtmpl': video_file + '.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            # 🔥 Add cookies support to bypass 403 Forbidden
            'cookiesfrombrowser': ('firefox',),  # Try Firefox cookies first
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},  # Use mobile client
        }
        
        # Try with Firefox cookies, fallback to Chrome, then no cookies
        browser_attempts = [
            ('firefox', 'Firefox'),
            ('chrome', 'Chrome'),
            (None, 'No cookies')
        ]
        
        video_downloaded = False
        for browser, browser_name in browser_attempts:
            if browser:
                video_opts['cookiesfrombrowser'] = (browser,)
                logger.info(f"🍪 Trying {browser_name} cookies...")
            else:
                video_opts.pop('cookiesfrombrowser', None)
                logger.info(f"🔓 Trying without cookies...")
            
            try:
                with yt_dlp.YoutubeDL(video_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    video_ext = info.get('ext', 'webm')
                    video_downloaded = True
                    logger.info(f"✅ Video downloaded using {browser_name}")
                    break
            except Exception as e:
                logger.warning(f"⚠️ Failed with {browser_name}: {str(e)[:100]}")
                continue
        
        if not video_downloaded:
            logger.error("❌ All browser cookie attempts failed for video")
            return None
        
        actual_video_file = f"{video_file}.{video_ext}"
        logger.info(f"✅ Video downloaded: {os.path.getsize(actual_video_file) / (1024*1024):.2f} MB ({video_ext})")
        
        # Download audio only (yt-dlp will add proper extension)
        logger.info("⬇️ Step 2/3: Downloading audio stream...")
        download_progress[task_id] = {
            'progress': 40,
            'status': 'downloading',
            'message': 'Đang tải audio stream...',
            'speed': None,
            'eta': None
        }
        
        audio_opts = {
            'format': audio_format,
            'outtmpl': audio_file + '.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            # 🔥 Use the same browser cookies for audio
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }
        
        # Try same browser sequence for audio
        audio_downloaded = False
        for browser, browser_name in browser_attempts:
            if browser:
                audio_opts['cookiesfrombrowser'] = (browser,)
            else:
                audio_opts.pop('cookiesfrombrowser', None)
            
            try:
                with yt_dlp.YoutubeDL(audio_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    audio_ext = info.get('ext', 'webm')
                    audio_downloaded = True
                    break
            except Exception as e:
                continue
        
        if not audio_downloaded:
            logger.error("❌ All browser cookie attempts failed for audio")
            return None
        
        actual_audio_file = f"{audio_file}.{audio_ext}"
        logger.info(f"✅ Audio downloaded: {os.path.getsize(actual_audio_file) / (1024*1024):.2f} MB ({audio_ext})")
        
        # Merge and convert to MP4 with FFmpeg
        logger.info("🔧 Step 3/3: Merging + converting to MP4 with FFmpeg...")
        download_progress[task_id] = {
            'progress': 70,
            'status': 'processing',
            'message': 'Đang merge video + audio và convert sang MP4...',
            'speed': None,
            'eta': None
        }
        
        final_output = output_path.replace('%(ext)s', 'mp4')
        
        # Detect if we need to re-encode video (WebM/VP9 -> H.264)
        if video_ext in ['webm', 'mkv']:
            logger.info("🔄 WebM/VP9 detected → Re-encoding to H.264 for MP4 compatibility")
            video_codec = 'libx264'
            video_params = ['-preset', 'medium', '-crf', '23']  # Good quality, reasonable speed
        else:
            logger.info("✅ Compatible video codec → Copying video stream")
            video_codec = 'copy'
            video_params = []
        
        # Build FFmpeg command
        cmd = [
            'ffmpeg', '-y',
            '-i', actual_video_file,
            '-i', actual_audio_file,
            '-c:v', video_codec,
        ] + video_params + [
            '-c:a', 'aac',           # Convert audio to AAC
            '-b:a', '192k',          # High quality audio bitrate
            '-movflags', '+faststart',  # Enable web streaming
            '-strict', 'experimental',
            final_output
        ]
        
        logger.info(f"📺 FFmpeg: {' '.join(cmd[0:10])}...")  # Log first part only
        
        # Run FFmpeg (blocking - simpler and more reliable)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            file_size = os.path.getsize(final_output) / (1024*1024)
            logger.info(f"✅ Merge + Convert successful: {file_size:.2f} MB")
            logger.info(f"✅ Output file: {final_output}")
            
            download_progress[task_id] = {
                'progress': 100,
                'status': 'completed',
                'message': 'Hoàn tất xử lý!',
                'speed': None,
                'eta': None
            }
            
            # Cleanup temp files
            try:
                if os.path.exists(actual_video_file):
                    os.remove(actual_video_file)
                if os.path.exists(actual_audio_file):
                    os.remove(actual_audio_file)
                logger.info("🧹 Temp files cleaned up")
            except Exception as e:
                logger.warning(f"⚠️ Cleanup warning: {e}")
            
            # Return the final output path
            return final_output
        else:
            logger.error(f"❌ FFmpeg merge failed!")
            logger.error(f"📋 Return code: {result.returncode}")
            logger.error(f"📋 stderr: {result.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Local merge error: {e}")
        import traceback
        logger.error(f"📋 Traceback:\n{traceback.format_exc()}")
        return None


def download_video(url: str, format_id: str, task_id: str, output_path: str, download_type: str = "video", audio_options: dict = None):
    """Download video or audio using yt-dlp with smart fallback"""
    logger.info(f"=== Starting download ===")
    logger.info(f"URL: {url}")
    logger.info(f"Format ID: {format_id}")
    logger.info(f"Download Type: {download_type}")
    logger.info(f"Output Path: {output_path}")
    if audio_options:
        logger.info(f"Audio Options: {audio_options}")
    
    download_progress[task_id] = {
        'progress': 0,
        'status': 'starting',
        'speed': None,
        'eta': None
    }
    
    # Base options with headers to bypass 403 errors
    ydl_opts = {
        'outtmpl': output_path,
        'progress_hooks': [lambda d: progress_hook(d, task_id)],
        'prefer_ffmpeg': True,
        'quiet': False,
        'verbose': True,  # Enable verbose for debugging
        # Critical options to bypass YouTube 403 errors
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
        # Add retry and sleep options
        'retries': 10,
        'fragment_retries': 10,
        'sleep_interval': 1,
        'max_sleep_interval': 5,
        # YouTube specific extractor args
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'player_skip': ['webpage', 'configs'],
            }
        },
    }
    
    if download_type == "audio":
        # Audio download - will process with FFmpeg after download
        audio_format_attempts = [
            format_id,  # Try user-selected format first
            'bestaudio',  # Best audio quality available
            'bestaudio[ext=m4a]',  # Best M4A audio
            'bestaudio*',  # Any best audio format
        ]

        audio_format_string = '/'.join(audio_format_attempts)

        # Download raw audio without postprocessing
        # We'll process it with FFmpeg after download for more control
        # Replace .%(ext)s with _raw.%(ext)s to avoid double extension
        temp_output = output_path.replace('.%(ext)s', '_raw.%(ext)s')
        ydl_opts.update({
            'format': audio_format_string,
            'outtmpl': temp_output,
        })
        logger.info(f"=== Audio download with format fallback: {audio_format_string}")
        logger.info(f"=== Temp output pattern: {temp_output}")
        logger.info(f"=== Will process with FFmpeg after download")
    else:
        # Video download with smart format selection and fallback
        format_attempts = []
        
        if '+' in format_id:
            # Merged format requested
            video_id, audio_id = format_id.split('+', 1)
            
            # 🚀 NEW STRATEGY: Try LOCAL MERGE first to bypass YouTube PO Token
            logger.info(f"🎯 Detected merge request: {video_id} + {audio_id}")
            logger.info(f"🔧 Attempting LOCAL merge (bypass YouTube PO Token restriction)...")
            
            merged_file = download_and_merge_local(url, video_id, audio_id, task_id, output_path)
            if merged_file:
                download_progress[task_id] = {
                    'progress': 100,
                    'status': 'completed',
                    'speed': None,
                    'eta': None,
                    'file_path': merged_file  # 🎯 Store the actual file path
                }
                logger.info(f"✅ LOCAL MERGE SUCCESS! File ready: {merged_file}")
                return True
            
            logger.warning(f"⚠️ Local merge failed, trying YouTube merge fallbacks...")
            format_attempts = [
                (format_id, f"YouTube merge: {format_id}"),
                (f"{video_id}+bestaudio", f"Video {video_id} + best audio"),
                (f"bestvideo[height<=2160]+bestaudio", "Best video (≤4K) + best audio"),
                (f"bestvideo+bestaudio", "Best video + audio"),
                ("best[height<=2160]", "Best single format (≤4K)"),
                ("best", "Best available format"),
            ]
        else:
            # Single format - detect format type and create compatible merges
            fmt_info = get_format_info(url, format_id)

            # Extract height from format info for HLS fallback
            height = fmt_info.get('height') if fmt_info else None

            # 🎯 TIKTOK FIX: TikTok formats already have video+audio embedded
            # Check if this is TikTok and format has both video and audio
            is_tiktok = 'tiktok.com' in url.lower() or 'vt.tiktok.com' in url.lower()
            has_both_streams = (fmt_info and
                              fmt_info.get('vcodec') != 'none' and
                              fmt_info.get('acodec') not in ['none', None])

            if is_tiktok and has_both_streams:
                logger.info(f"🎵 TikTok format with embedded audio detected: {format_id}")
                logger.info(f"🎵 Video codec: {fmt_info.get('vcodec')}, Audio codec: {fmt_info.get('acodec')}")
                logger.info(f"🎵 Downloading directly without merge...")

                # TikTok formats already have audio - download directly
                format_attempts = [
                    (format_id, f"TikTok: {format_id} (embedded audio)"),
                    ("best", "TikTok: Best available format"),
                ]
            elif fmt_info and fmt_info.get('vcodec') != 'none' and fmt_info.get('acodec') == 'none':
                # 🚀 Try LOCAL MERGE for video-only formats (YouTube/Facebook)
                logger.info(f"🎬 Video-only format detected: {format_id}")

                # Determine best audio format
                if fmt_info.get('ext') == 'webm':
                    audio_format = '251'  # Opus audio for WebM
                    logger.info(f"🎬 WebM video - using Opus audio (251)")
                else:
                    audio_format = '140'  # M4A audio for MP4
                    logger.info(f"🎬 MP4 video - using M4A audio (140)")

                logger.info(f"🔧 Attempting LOCAL merge: {format_id} + {audio_format}...")
                merged_file = download_and_merge_local(url, format_id, audio_format, task_id, output_path)
                if merged_file:
                    download_progress[task_id] = {
                        'progress': 100,
                        'status': 'completed',
                        'speed': None,
                        'eta': None,
                        'file_path': merged_file  # 🎯 Store the actual file path
                    }
                    logger.info(f"✅ LOCAL MERGE SUCCESS! File ready: {merged_file}")
                    return True

                logger.warning(f"⚠️ Local merge failed, trying YouTube merge...")

            if is_tiktok and has_both_streams:
                # Already set format_attempts above for TikTok
                pass
            elif fmt_info and fmt_info.get('ext') == 'webm':
                # WebM format - prefer opus/webm audio
                logger.info(f"🎬 WebM video detected, using WebM-compatible audio")
                format_attempts = [
                    (f"{format_id}+251", f"Format {format_id} + opus audio"),
                    (f"{format_id}+250", f"Format {format_id} + opus audio (low)"),
                    (f"{format_id}+bestaudio[ext=webm]", f"Format {format_id} + webm audio"),
                    (f"{format_id}+bestaudio", f"Format {format_id} + best audio"),
                ]
            else:
                # MP4 or other format - prefer m4a audio
                logger.info(f"🎬 MP4 video detected, using M4A-compatible audio")
                format_attempts = [
                    (f"{format_id}+140", f"Format {format_id} + m4a audio (128k)"),
                    (f"{format_id}+139", f"Format {format_id} + m4a audio (48k)"),
                    (f"{format_id}+bestaudio[ext=m4a]", f"Format {format_id} + m4a audio"),
                    (f"{format_id}+bestaudio", f"Format {format_id} + best audio"),
                ]
            
            # Add HLS/M3U8 fallback for YouTube PO Token issue
            # CRITICAL: HLS formats CANNOT be merged due to YouTube restrictions
            # HLS formats have embedded audio - download as single file ONLY
            if height:
                if height >= 2160:
                    format_attempts.extend([
                        ("96", "✅ HLS: 1080p/4K (no merge - embedded audio)"),
                    ])
                elif height >= 1080:
                    format_attempts.extend([
                        ("96", "✅ HLS: 1080p (no merge - embedded audio)"),
                    ])
                elif height >= 720:
                    format_attempts.extend([
                        ("95", "✅ HLS: 720p (no merge - embedded audio)"),
                    ])
                elif height >= 480:
                    format_attempts.extend([
                        ("94", "✅ HLS: 480p (no merge - embedded audio)"),
                    ])
                else:
                    format_attempts.extend([
                        ("93", "✅ HLS: 360p (no merge - embedded audio)"),
                    ])
            
            # Generic HLS fallbacks - NO MERGE ALLOWED
            format_attempts.extend([
                ("96", "✅ HLS: Best quality (1080p/4K)"),
                ("95", "✅ HLS: 720p"),
                ("94", "✅ HLS: 480p"),
                ("93", "✅ HLS: 360p"),
                # Last resort: format 18 (360p with audio, HTTP)
                ("18", "⚠️ HTTP: 360p (last resort)"),
            ])
            
            # Filter out None values
            format_attempts = [(f, d) for f, d in format_attempts if f is not None]
        
        # Try each format strategy
        for idx, (format_str, description) in enumerate(format_attempts):
            try:
                logger.info(f"=== Attempt {idx + 1}/{len(format_attempts)}: {description}")
                logger.info(f"=== Format string: {format_str}")
                
                current_opts = ydl_opts.copy()
                current_opts['format'] = format_str
                current_opts['merge_output_format'] = 'mp4'
                
                with yt_dlp.YoutubeDL(current_opts) as ydl:
                    ydl.download([url])

                # Check for downloaded file and re-encode AV1 if needed
                downloaded_file = output_path.replace('.%(ext)s', '.mp4')
                if os.path.exists(downloaded_file):
                    logger.info(f"📁 Checking video codec for: {downloaded_file}")
                    check_and_reencode_av1(downloaded_file, task_id)
                else:
                    logger.warning(f"⚠️ Downloaded file not found at expected path: {downloaded_file}")

                download_progress[task_id] = {
                    'progress': 100,
                    'status': 'completed',
                    'speed': None,
                    'eta': None
                }
                logger.info(f"✅ Download succeeded with: {description}")
                return True
                
            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e)
                logger.warning(f"⚠️ Attempt {idx + 1} failed: {error_msg[:100]}...")
                
                # If this is the last attempt, fail
                if idx == len(format_attempts) - 1:
                    logger.error(f"❌ All {len(format_attempts)} attempts failed")
                    download_progress[task_id] = {
                        'progress': 0,
                        'status': f'error: {error_msg}',
                        'speed': None,
                        'eta': None
                    }
                    return False
                
                # Continue to next attempt
                continue
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"⚠️ Unexpected error in attempt {idx + 1}: {error_msg[:100]}...")
                
                # If this is the last attempt, fail
                if idx == len(format_attempts) - 1:
                    logger.error(f"❌ All attempts exhausted")
                    download_progress[task_id] = {
                        'progress': 0,
                        'status': f'error: {error_msg}',
                        'speed': None,
                        'eta': None
                    }
                    return False
                
                continue
        
        # This should not be reached
        return False
    
    # For audio downloads
    try:
        logger.info("=== Attempting audio download...")

        # Step 1: Download raw audio
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        logger.info("✅ Raw audio downloaded!")

        # Step 2: Find the downloaded file
        import glob
        temp_dir = os.path.dirname(output_path)

        # Remove .%(ext)s from output_path to get base path, then add _raw.*
        base_path = output_path.replace('.%(ext)s', '')
        raw_pattern = base_path + "_raw.*"

        logger.info(f"🔍 Searching for raw audio with pattern: {raw_pattern}")
        raw_files = glob.glob(raw_pattern)

        if not raw_files:
            logger.error(f"❌ Could not find downloaded audio file!")
            logger.error(f"❌ Pattern used: {raw_pattern}")
            logger.error(f"❌ Temp dir contents: {list(Path(temp_dir).iterdir())}")
            raise Exception("Downloaded audio file not found")

        raw_audio_file = raw_files[0]
        logger.info(f"📁 Raw audio file: {raw_audio_file}")

        # Step 3: Process with FFmpeg if audio_options provided
        if audio_options:
            logger.info("🎵 Processing audio with FFmpeg...")

            # Determine output extension based on codec
            codec = audio_options.get('codec', 'mp3')
            ext_map = {
                'mp3': '.mp3',
                'm4a': '.m4a',
                'opus': '.opus',
                'copy': os.path.splitext(raw_audio_file)[1]  # Keep original extension
            }
            output_ext = ext_map.get(codec, '.mp3')

            # Remove .%(ext)s from output_path before adding new extension
            base_output = output_path.replace('.%(ext)s', '')
            final_output = base_output + output_ext

            # Process audio
            success = process_audio_with_ffmpeg(
                raw_audio_file,
                final_output,
                audio_options,
                task_id
            )

            # Clean up raw file
            try:
                os.remove(raw_audio_file)
                logger.info(f"🗑️  Removed raw audio file")
            except:
                pass

            if not success:
                raise Exception("FFmpeg audio processing failed")

            logger.info(f"✅ Audio processing completed: {final_output}")

            # Update file path in task tracking
            download_progress[task_id]['file_path'] = final_output

        else:
            # No custom options - just use default MP3 conversion
            logger.info("🎵 Using default MP3 conversion...")

            # Remove .%(ext)s from output_path before adding .mp3
            base_output = output_path.replace('.%(ext)s', '')
            final_output = base_output + ".mp3"

            # Simple FFmpeg conversion
            import subprocess
            cmd = ['ffmpeg', '-y', '-i', raw_audio_file, '-c:a', 'libmp3lame', '-b:a', '192k', final_output]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode != 0:
                logger.error(f"❌ FFmpeg conversion failed: {result.stderr}")
                raise Exception("FFmpeg conversion failed")

            # Clean up raw file
            try:
                os.remove(raw_audio_file)
            except:
                pass

            logger.info(f"✅ MP3 conversion completed: {final_output}")
            download_progress[task_id]['file_path'] = final_output

        download_progress[task_id].update({
            'progress': 100,
            'status': 'completed',
            'speed': None,
            'eta': None
        })
        logger.info("✅ Audio download and processing completed!")
        return True


    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Audio download failed: {error_msg}")
        download_progress[task_id] = {
            'progress': 0,
            'status': f'error: {error_msg}',
            'speed': None,
            'eta': None
        }
        return False


# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Video Downloader API"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    if db:
        doc = status_obj.model_dump()
        doc['timestamp'] = doc['timestamp'].isoformat()
        _ = await db.status_checks.insert_one(doc)
    
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    if not db:
        return []
    
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks


@api_router.post("/analyze", response_model=VideoInfo)
async def analyze_video(request: VideoAnalyzeRequest):
    """Analyze video URL and return available formats"""
    logger.info("="*80)
    logger.info(f"🔍 ANALYZE REQUEST")
    logger.info(f"🔗 URL: {request.url}")
    logger.info("="*80)
    
    try:
        # Run blocking operation in thread pool
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(executor, extract_video_info, request.url)
        
        # Extract source platform
        source = info.get('extractor_key', 'Unknown')
        
        # Parse formats and create smart combinations
        formats_list = []
        audio_formats = []
        video_only_formats = []
        seen_qualities = set()
        best_audio_id = None
        
        # Dictionary to store best format for each resolution
        # Key: (height, fps_key), Value: format_info
        best_formats_by_resolution = {}
        
        # First pass: identify all formats
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
            
            # Collect audio only formats
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
            
            # Key for deduplication: (height, fps)
            fps_key = fps if fps else 0
            resolution_key = (height, fps_key)
            
            # Store video info
            video_info = {
                'format_id': format_id,
                'quality': quality,
                'resolution': f"{fmt.get('width', 0)}x{height}",
                'fps': fps,
                'filesize': filesize,
                'ext': ext,
                'vcodec': vcodec,
                'acodec': acodec if acodec != 'none' else None,
                'has_audio': has_audio,
                'has_video': has_video,
                'height': height,
                'format_note': format_note
            }
            
            # Check if we should replace existing format for this resolution
            # Priority: format with filesize > format without filesize
            if resolution_key in best_formats_by_resolution:
                existing = best_formats_by_resolution[resolution_key]
                # Replace if: current has filesize and existing doesn't
                if filesize and not existing['filesize']:
                    best_formats_by_resolution[resolution_key] = video_info
                # Or if both have/don't have filesize, prefer has_audio
                elif (bool(filesize) == bool(existing['filesize'])) and has_audio and not existing['has_audio']:
                    best_formats_by_resolution[resolution_key] = video_info
            else:
                best_formats_by_resolution[resolution_key] = video_info
        
        # Get best audio format for merging (prefer m4a/mp4 audio for better compatibility)
        if audio_formats:
            # Prioritize m4a/mp4 audio, then sort by bitrate
            audio_formats.sort(key=lambda x: (
                1 if x['ext'] in ['m4a', 'mp4'] else 0,
                x['abr']
            ), reverse=True)
            best_audio_id = audio_formats[0]['format_id']
            logger.info(f"📻 Best audio format selected: {best_audio_id} ({audio_formats[0]['quality']})")
        
        # Second pass: create format list from best formats
        for resolution_key, vid_fmt in best_formats_by_resolution.items():
            format_id = vid_fmt['format_id']
            video_ext = vid_fmt['ext']
            has_audio = vid_fmt['has_audio']
            
            # If format already has audio, use it directly
            if has_audio:
                formats_list.append(VideoFormat(
                    format_id=format_id,
                    quality=f"{vid_fmt['quality']}",
                    resolution=vid_fmt['resolution'],
                    fps=vid_fmt['fps'],
                    filesize=format_filesize(vid_fmt['filesize']) if vid_fmt['filesize'] else "Unknown",
                    ext=video_ext,
                    vcodec=vid_fmt['vcodec'],
                    acodec=vid_fmt['acodec'],
                    has_audio=True,
                    has_video=True,
                    format_note=vid_fmt['format_note']
                ))
            else:
                # Video only - need to merge with audio
                # Determine best audio based on video container
                if video_ext == 'webm' and audio_formats:
                    webm_audio = next((a for a in audio_formats if a['ext'] in ['webm', 'opus']), audio_formats[0])
                    best_compatible_audio = webm_audio['format_id']
                    audio_codec = webm_audio['acodec']
                elif audio_formats:
                    m4a_audio = next((a for a in audio_formats if a['ext'] in ['m4a', 'mp4']), audio_formats[0])
                    best_compatible_audio = m4a_audio['format_id']
                    audio_codec = m4a_audio['acodec']
                else:
                    best_compatible_audio = "auto"
                    audio_codec = "auto"
                
                formats_list.append(VideoFormat(
                    format_id=format_id,
                    quality=f"{vid_fmt['quality']}",
                    resolution=vid_fmt['resolution'],
                    fps=vid_fmt['fps'],
                    filesize=format_filesize(vid_fmt['filesize']) if vid_fmt['filesize'] else "Unknown",
                    ext=video_ext,
                    vcodec=vid_fmt['vcodec'],
                    acodec=audio_codec,
                    has_audio=True,
                    has_video=True,
                    format_note=f"merge_audio:{best_compatible_audio}"
                ))
        
        # Sort by resolution first (prioritize 4K), then has_audio, then fps
        formats_list.sort(
            key=lambda x: (
                int(x.quality.split('p')[0]) if 'p' in x.quality else 0,  # Resolution (4K = 2160p first)
                x.has_audio,  # Then formats with audio
                x.fps if x.fps else 0  # Then higher fps
            ),
            reverse=True
        )
        
        # Add audio-only MP3 options (deduplicated by bitrate)
        seen_audio_bitrates = set()
        unique_audio_formats = []
        for audio_fmt in audio_formats:
            # Use bitrate as key for deduplication
            abr_key = int(audio_fmt['abr']) if audio_fmt['abr'] else 0
            if abr_key not in seen_audio_bitrates:
                seen_audio_bitrates.add(abr_key)
                unique_audio_formats.append(audio_fmt)
        
        # Sort by bitrate descending and take top 3 unique
        unique_audio_formats.sort(key=lambda x: x['abr'], reverse=True)
        for audio_fmt in unique_audio_formats[:3]:
            bitrate_label = f"{int(audio_fmt['abr'])}kbps" if audio_fmt['abr'] else "Auto"
            formats_list.append(VideoFormat(
                format_id=audio_fmt['format_id'],
                quality=f"Audio - {bitrate_label}",
                resolution=None,
                fps=None,
                filesize=format_filesize(audio_fmt['filesize']) if audio_fmt['filesize'] else "Unknown",
                ext='mp3',
                vcodec=None,
                acodec=audio_fmt['acodec'],
                has_audio=True,
                has_video=False,
                format_note=f"Audio only ({audio_fmt['ext']})"
            ))
        
        # Convert duration to int if float
        duration = info.get('duration')
        if duration and isinstance(duration, float):
            duration = int(duration)
        
        # Return top 20 formats to include 4K options
        video_result = VideoInfo(
            title=info.get('title', 'Unknown'),
            thumbnail=info.get('thumbnail'),
            duration=duration,
            source=source,
            formats=formats_list[:20]
        )
        
        logger.info(f"✅ Analysis completed successfully")
        logger.info(f"🎬 Title: {video_result.title}")
        logger.info(f"📊 Formats returned: {len(video_result.formats)}")
        logger.info("="*80)
        
        return video_result
        
    except Exception as e:
        logger.error("="*80)
        logger.error(f"❌ ANALYSIS ERROR")
        logger.error(f"❌ Error type: {type(e).__name__}")
        logger.error(f"❌ Error message: {str(e)}")
        logger.error("="*80)
        import traceback
        logger.error(f"📋 Full traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Failed to analyze video: {str(e)}")


@api_router.post("/download")
async def download_video_endpoint(request: DownloadRequest, background_tasks: BackgroundTasks):
    """Start download task and return task_id for polling"""
    task_id = str(uuid.uuid4())
    
    logger.info("="*80)
    logger.info(f"📥 NEW DOWNLOAD REQUEST - Task ID: {task_id}")
    logger.info(f"🔗 URL: {request.url}")
    logger.info(f"📊 Format ID: {request.format_id}")
    logger.info(f"🎬 Type: {request.download_type}")
    logger.info("="*80)
    
    # Initialize task status
    download_progress[task_id] = {
        'progress': 0,
        'status': 'starting',
        'message': 'Initializing download...'
    }
    
    # Create temporary directory for this download
    temp_dir = tempfile.mkdtemp()
    output_template = os.path.join(temp_dir, 'download.%(ext)s')
    
    logger.info(f"📁 Temp directory: {temp_dir}")
    
    # Store task info
    task_files[task_id] = {
        'temp_dir': temp_dir,
        'ready': False,
        'created_at': datetime.now(timezone.utc),
        'download_type': request.download_type
    }
    
    # Start download in background
    async def download_task():
        try:
            loop = asyncio.get_event_loop()

            # Convert audio_options to dict if present
            audio_opts_dict = None
            if request.audio_options:
                audio_opts_dict = request.audio_options.model_dump()

            success = await loop.run_in_executor(
                executor,
                download_video,
                request.url,
                request.format_id,
                task_id,
                output_template,
                request.download_type,
                audio_opts_dict
            )
            
            if not success:
                logger.error(f"❌ Download failed for task {task_id}")
                task_files[task_id]['ready'] = False
                task_files[task_id]['error'] = 'Download failed'
                download_progress[task_id]['status'] = 'error'
                return
            
            # Check if we have a specific file path from local merge
            progress_data = download_progress.get(task_id, {})
            if 'file_path' in progress_data:
                downloaded_file = Path(progress_data['file_path'])
                logger.info(f"✅ Using local merge file: {downloaded_file}")
            else:
                files = list(Path(temp_dir).glob('download.*'))
                if not files:
                    logger.error(f"❌ Downloaded file not found in {temp_dir}")
                    task_files[task_id]['ready'] = False
                    task_files[task_id]['error'] = 'File not found'
                    return
                downloaded_file = files[0]
            
            file_size = downloaded_file.stat().st_size
            logger.info(f"✅ File ready: {downloaded_file.name} ({file_size / (1024*1024):.2f} MB)")
            
            # Copy file to downloads directory for static serving
            # Use task_id as filename to avoid conflicts, frontend will provide custom name
            file_extension = downloaded_file.suffix  # .mp4 or .mp3
            static_filename = f"{task_id}{file_extension}"
            static_file_path = DOWNLOADS_DIR / static_filename
            
            shutil.copy2(downloaded_file, static_file_path)
            logger.info(f"📋 Copied file to downloads: {static_filename}")
            
            # Mark as ready with static file URL
            task_files[task_id]['file_path'] = str(downloaded_file)  # Keep original for cleanup
            task_files[task_id]['static_path'] = str(static_file_path)  # Static file path
            task_files[task_id]['static_url'] = f"/downloads/{static_filename}"  # URL to access
            task_files[task_id]['file_size'] = file_size
            task_files[task_id]['ready'] = True
            task_files[task_id]['file_extension'] = file_extension  # Store extension only
            
            download_progress[task_id] = {
                'progress': 100,
                'status': 'completed',
                'message': 'File ready for download'
            }
            
            logger.info(f"🎉 Task {task_id} completed and ready! URL: /downloads/{static_filename}")
            
        except Exception as e:
            logger.error(f"❌ Error in download task {task_id}: {e}")
            task_files[task_id]['ready'] = False
            task_files[task_id]['error'] = str(e)
            download_progress[task_id]['status'] = 'error'
            download_progress[task_id]['message'] = str(e)
    
    # Start background task
    background_tasks.add_task(download_task)
    
    # Return task_id immediately
    return {
        'task_id': task_id,
        'status': 'started',
        'message': 'Download started. Use /api/download/status/{task_id} to check progress.'
    }


# New endpoint: Check download status
@api_router.get("/download/status/{task_id}")
async def check_download_status(task_id: str):
    """Check if download is ready"""
    if task_id not in task_files:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task_info = task_files[task_id]
    progress_info = download_progress.get(task_id, {})
    
    return {
        'task_id': task_id,
        'ready': task_info.get('ready', False),
        'progress': progress_info.get('progress', 0),
        'status': progress_info.get('status', 'unknown'),
        'message': progress_info.get('message', ''),
        'error': task_info.get('error'),
        'file_size': task_info.get('file_size'),
        'download_url': f"/download/file/{task_id}",  # Relative path (API prefix added by router)
        'file_extension': task_info.get('file_extension', '.mp4')  # Return extension for frontend
    }


# Endpoint: Download ready file with proper attachment header
@api_router.get("/download/file/{task_id}")
async def download_ready_file(task_id: str, custom_filename: Optional[str] = None):
    """Serve file with Content-Disposition: attachment to force download"""
    if task_id not in task_files:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task_info = task_files[task_id]
    
    if not task_info.get('ready'):
        raise HTTPException(status_code=425, detail="File not ready yet")
    
    static_path = task_info.get('static_path')
    if not static_path or not os.path.exists(static_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get file extension
    file_extension = task_info.get('file_extension', '.mp4')
    
    # Use custom filename if provided, otherwise use generic name
    if custom_filename:
        filename = custom_filename
        # Ensure filename has correct extension
        if not filename.endswith(('.mp4', '.mp3')):
            filename = f"{filename}{file_extension}"
    else:
        # Fallback to generic name if frontend doesn't provide custom name
        filename = "audio.mp3" if file_extension == '.mp3' else "video.mp4"
    
    media_type = "audio/mpeg" if filename.endswith('.mp3') else "video/mp4"
    
    logger.info(f"📥 Serving file for download: {filename}")
    
    from fastapi.responses import FileResponse
    return FileResponse(
        path=static_path,
        media_type=media_type,
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


# Endpoint: Cleanup after download
@api_router.delete("/download/cleanup/{task_id}")
async def cleanup_download(task_id: str):
    """Cleanup task files after successful download"""
    if task_id not in task_files:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task_info = task_files[task_id]
    temp_dir = task_info.get('temp_dir')
    
    try:
        # Clean up temp directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"🧹 Cleaned up temp directory for task {task_id}")
        
        # Clean up static file
        static_path = task_info.get('static_path')
        if static_path and os.path.exists(static_path):
            os.remove(static_path)
            logger.info(f"🧹 Cleaned up static file for task {task_id}")
        
        # Remove from tracking dicts
        del task_files[task_id]
        if task_id in download_progress:
            del download_progress[task_id]
        
        return {'status': 'cleaned', 'task_id': task_id}
    except Exception as e:
        logger.error(f"❌ Cleanup error for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        logger.error(f"❌ Error type: {type(e).__name__}")
        logger.error(f"❌ Error message: {str(e)}")
        logger.error(f"❌ Task ID: {task_id}")
        logger.error("="*80)
        import traceback
        logger.error(f"📋 Full traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


# ===== AUDIO EDITOR ENDPOINTS =====

@api_router.post("/audio/upload")
async def upload_audio(audio_file: UploadFile = File(...)):
    """Upload an audio or video file for editing (video will have audio extracted)"""
    try:
        # Check file type
        content_type = audio_file.content_type or ''
        is_audio = content_type.startswith('audio/')
        is_video = content_type.startswith('video/')

        if not is_audio and not is_video:
            raise HTTPException(
                status_code=400,
                detail="Only audio or video files are allowed"
            )

        # Generate unique audio ID
        audio_id = str(uuid.uuid4())

        # Save file to uploads directory
        file_extension = os.path.splitext(audio_file.filename)[1] or ('.mp3' if is_audio else '.mp4')
        file_path = UPLOADS_DIR / f"{audio_id}{file_extension}"

        # Write file
        with open(file_path, 'wb') as f:
            content = await audio_file.read()
            f.write(content)

        # Store original filename for later use
        uploaded_audio_files[audio_id] = audio_file.filename

        logger.info(f"📤 Uploaded {'video' if is_video else 'audio'} file: {audio_file.filename} -> {audio_id}")

        return {
            'audio_id': audio_id,
            'filename': audio_file.filename,
            'size': len(content),
            'is_video': is_video
        }

    except Exception as e:
        logger.error(f"❌ Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AudioProcessRequest(BaseModel):
    audio_id: str
    options: dict  # Same structure as AudioOptions


@api_router.post("/audio/process")
async def process_audio(request: AudioProcessRequest, background_tasks: BackgroundTasks):
    """Process uploaded audio file with editing options"""
    audio_id = request.audio_id
    options = request.options

    # Check if audio file exists
    audio_files = list(UPLOADS_DIR.glob(f"{audio_id}*"))
    if not audio_files:
        raise HTTPException(status_code=404, detail="Audio file not found")

    input_file = str(audio_files[0])
    # Get original filename from tracking dict
    original_filename = uploaded_audio_files.get(audio_id, "audio")
    # Remove extension from original filename to add new codec extension later
    original_basename = os.path.splitext(original_filename)[0]

    logger.info(f"🔍 Debug - audio_id: {audio_id}")
    logger.info(f"🔍 Debug - original_filename from dict: {original_filename}")
    logger.info(f"🔍 Debug - original_basename: {original_basename}")

    task_id = str(uuid.uuid4())

    # Create temp directory for processing
    temp_dir = tempfile.mkdtemp(prefix=f"audio_edit_{task_id}_")

    # Check if input is video and extract audio first
    input_ext = os.path.splitext(input_file)[1].lower()
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v']

    if input_ext in video_extensions:
        logger.info(f"🎬 Detected video file, extracting audio...")
        # Extract audio from video
        extracted_audio = os.path.join(temp_dir, f"extracted_audio.wav")
        try:
            import subprocess
            extract_cmd = ['ffmpeg', '-y', '-i', input_file, '-vn', '-acodec', 'pcm_s16le', extracted_audio]
            result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                logger.error(f"❌ Audio extraction failed: {result.stderr}")
                raise Exception("Failed to extract audio from video")
            logger.info(f"✅ Audio extracted successfully")
            input_file = extracted_audio  # Use extracted audio as input
        except Exception as e:
            logger.error(f"❌ Error extracting audio from video: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to extract audio from video: {str(e)}")

    # Determine output extension based on codec
    codec = options.get('codec', 'mp3')
    if codec == 'mp3':
        output_ext = '.mp3'
    elif codec == 'm4a':
        output_ext = '.m4a'
    elif codec == 'opus':
        output_ext = '.opus'
    elif codec == 'flac':
        output_ext = '.flac'
    elif codec == 'wav':
        output_ext = '.wav'
    elif codec == 'copy':
        # Keep original extension
        output_ext = os.path.splitext(input_file)[1]
    else:
        output_ext = '.mp3'

    output_file = os.path.join(temp_dir, f"processed{output_ext}")

    # Initialize task tracking
    audio_tasks[task_id] = {
        'audio_id': audio_id,
        'temp_dir': temp_dir,
        'output_file': output_file,
        'status': 'processing',
        'progress': 0,
        'ready': False,
        'error': None,
        'file_extension': output_ext,
        'original_basename': original_basename,  # Store original filename without extension
        'created_at': datetime.now(timezone.utc)
    }

    # Process in background
    async def process_task():
        try:
            logger.info(f"🎵 Starting audio processing for task {task_id}")
            audio_tasks[task_id]['status'] = 'processing'
            audio_tasks[task_id]['progress'] = 10

            # Run FFmpeg processing
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                executor,
                process_audio_with_ffmpeg,
                input_file,
                output_file,
                options,
                task_id
            )

            if not success:
                raise Exception("FFmpeg processing failed")

            audio_tasks[task_id]['progress'] = 80

            # Move processed file to downloads directory
            static_filename = f"{task_id}{output_ext}"
            static_path = DOWNLOADS_DIR / static_filename
            shutil.copy(output_file, static_path)

            audio_tasks[task_id]['static_path'] = str(static_path)
            audio_tasks[task_id]['progress'] = 100
            audio_tasks[task_id]['status'] = 'completed'
            audio_tasks[task_id]['ready'] = True

            logger.info(f"✅ Audio processing completed for task {task_id}")

        except Exception as e:
            logger.error(f"❌ Audio processing error for task {task_id}: {e}")
            audio_tasks[task_id]['status'] = 'error'
            audio_tasks[task_id]['error'] = str(e)

    background_tasks.add_task(process_task)

    return {'task_id': task_id, 'status': 'processing'}


@api_router.get("/audio/status/{task_id}")
async def get_audio_status(task_id: str):
    """Get audio processing status"""
    if task_id not in audio_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task_info = audio_tasks[task_id]

    return {
        'task_id': task_id,
        'ready': task_info.get('ready', False),
        'progress': task_info.get('progress', 0),
        'status': task_info.get('status', 'unknown'),
        'error': task_info.get('error'),
        'download_url': f"/audio/download/{task_id}" if task_info.get('ready') else None,
        'file_extension': task_info.get('file_extension', '.mp3')
    }


@api_router.get("/audio/download/{task_id}")
async def download_processed_audio(task_id: str):
    """Download processed audio file"""
    if task_id not in audio_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task_info = audio_tasks[task_id]

    if not task_info.get('ready'):
        raise HTTPException(status_code=425, detail="File not ready yet")

    static_path = task_info.get('static_path')
    if not static_path or not os.path.exists(static_path):
        raise HTTPException(status_code=404, detail="File not found")

    file_extension = task_info.get('file_extension', '.mp3')
    # Use original filename with new extension
    original_basename = task_info.get('original_basename', 'edited_audio')
    filename = f"{original_basename}{file_extension}"

    logger.info(f"🔍 Debug download - task_id: {task_id}")
    logger.info(f"🔍 Debug download - original_basename from task: {original_basename}")
    logger.info(f"🔍 Debug download - final filename: {filename}")

    media_type_map = {
        '.mp3': 'audio/mpeg',
        '.m4a': 'audio/mp4',
        '.opus': 'audio/opus',
        '.flac': 'audio/flac',
        '.wav': 'audio/wav'
    }
    media_type = media_type_map.get(file_extension, 'audio/mpeg')

    logger.info(f"📥 Serving processed audio: {filename}")

    from fastapi.responses import FileResponse
    return FileResponse(
        path=static_path,
        media_type=media_type,
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@api_router.delete("/audio/cleanup/{task_id}")
async def cleanup_audio_task(task_id: str):
    """Cleanup audio processing task files"""
    if task_id not in audio_tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task_info = audio_tasks[task_id]
    audio_id = task_info.get('audio_id')

    try:
        # Clean up temp directory
        temp_dir = task_info.get('temp_dir')
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"🧹 Cleaned up temp directory for audio task {task_id}")

        # Clean up static file
        static_path = task_info.get('static_path')
        if static_path and os.path.exists(static_path):
            os.remove(static_path)
            logger.info(f"🧹 Cleaned up processed file for audio task {task_id}")

        # Clean up uploaded file
        if audio_id:
            audio_files = list(UPLOADS_DIR.glob(f"{audio_id}*"))
            for audio_file in audio_files:
                os.remove(audio_file)
                logger.info(f"🧹 Cleaned up uploaded file: {audio_file}")

            # Remove from uploaded files tracking
            if audio_id in uploaded_audio_files:
                del uploaded_audio_files[audio_id]

        # Remove from tracking dict
        del audio_tasks[task_id]

        return {'status': 'cleaned', 'task_id': task_id}

    except Exception as e:
        logger.error(f"❌ Cleanup error for audio task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== END AUDIO EDITOR ENDPOINTS =====


@api_router.get("/progress/{task_id}", response_model=ProgressResponse)
async def get_progress(task_id: str):
    """Get download progress for a task"""
    if task_id not in download_progress:
        raise HTTPException(status_code=404, detail="Task not found")

    progress_data = download_progress[task_id]
    return ProgressResponse(**progress_data)


# Root route
@app.get("/")
async def root():
    return {"message": "DLVideo API is running", "status": "healthy"}

# Include the routers in the main app
app.include_router(api_router)
app.include_router(auth_router)

# Mount static files for downloads
from fastapi.staticfiles import StaticFiles
app.mount("/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', 'http://localhost:3000').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add authentication middleware (MUST be after CORS middleware)
app.add_middleware(AuthMiddleware)

# Configure logging with file handler
from logging.handlers import RotatingFileHandler

# Create logs directory if not exists
log_dir = ROOT_DIR / 'logs'
log_dir.mkdir(exist_ok=True)
log_file = log_dir / 'debug.log'

# Configure logging to both console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # Console handler
        logging.StreamHandler(),
        # File handler with rotation (max 10MB, keep 5 backup files)
        RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
    ]
)
logger = logging.getLogger(__name__)

logger.info("="*80)
logger.info("🚀 DLVideo API Server Starting...")
logger.info(f"📁 Log file: {log_file}")
logger.info("="*80)

@app.on_event("startup")
async def cleanup_old_temp_directories():
    """
    Clean up old temporary directories and orphaned files on server startup.
    This prevents disk space waste from interrupted downloads/re-encoding.
    """
    import glob
    import time

    try:
        current_time = time.time()
        # Clean up files/directories older than 1 hour (to avoid deleting active tasks)
        max_age_seconds = 3600

        total_cleaned_count = 0
        total_cleaned_size = 0

        # 1. Clean up system temp directories
        temp_dir = tempfile.gettempdir()
        pattern = os.path.join(temp_dir, 'tmp*')

        temp_cleaned_count = 0
        temp_cleaned_size = 0

        for temp_path in glob.glob(pattern):
            if os.path.isdir(temp_path):
                try:
                    # Check directory age
                    dir_mtime = os.path.getmtime(temp_path)
                    age_seconds = current_time - dir_mtime

                    if age_seconds > max_age_seconds:
                        # Calculate size before deletion
                        dir_size = sum(
                            os.path.getsize(os.path.join(dirpath, filename))
                            for dirpath, _, filenames in os.walk(temp_path)
                            for filename in filenames
                        )

                        # Delete directory
                        shutil.rmtree(temp_path)
                        temp_cleaned_count += 1
                        temp_cleaned_size += dir_size
                        logger.info(f"🧹 Cleaned old temp dir: {os.path.basename(temp_path)} ({dir_size / (1024*1024):.1f} MB)")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to clean {temp_path}: {e}")

        total_cleaned_count += temp_cleaned_count
        total_cleaned_size += temp_cleaned_size

        if temp_cleaned_count > 0:
            logger.info(f"✅ Temp directories: Removed {temp_cleaned_count} directories, freed {temp_cleaned_size / (1024*1024):.1f} MB")

        # 2. Clean up old files in downloads directory
        downloads_cleaned_count = 0
        downloads_cleaned_size = 0

        if DOWNLOADS_DIR.exists():
            for file_path in DOWNLOADS_DIR.glob('*'):
                if file_path.is_file():
                    try:
                        file_mtime = os.path.getmtime(file_path)
                        age_seconds = current_time - file_mtime

                        if age_seconds > max_age_seconds:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            downloads_cleaned_count += 1
                            downloads_cleaned_size += file_size
                            logger.info(f"🧹 Cleaned old download: {file_path.name} ({file_size / (1024*1024):.1f} MB)")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to clean {file_path}: {e}")

        total_cleaned_count += downloads_cleaned_count
        total_cleaned_size += downloads_cleaned_size

        if downloads_cleaned_count > 0:
            logger.info(f"✅ Downloads: Removed {downloads_cleaned_count} files, freed {downloads_cleaned_size / (1024*1024):.1f} MB")

        # 3. Clean up old files in uploads directory
        uploads_cleaned_count = 0
        uploads_cleaned_size = 0

        if UPLOADS_DIR.exists():
            for file_path in UPLOADS_DIR.glob('*'):
                if file_path.is_file():
                    try:
                        file_mtime = os.path.getmtime(file_path)
                        age_seconds = current_time - file_mtime

                        if age_seconds > max_age_seconds:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            uploads_cleaned_count += 1
                            uploads_cleaned_size += file_size
                            logger.info(f"🧹 Cleaned old upload: {file_path.name} ({file_size / (1024*1024):.1f} MB)")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to clean {file_path}: {e}")

        total_cleaned_count += uploads_cleaned_count
        total_cleaned_size += uploads_cleaned_size

        if uploads_cleaned_count > 0:
            logger.info(f"✅ Uploads: Removed {uploads_cleaned_count} files, freed {uploads_cleaned_size / (1024*1024):.1f} MB")

        # Summary
        if total_cleaned_count > 0:
            logger.info(f"🎉 Startup cleanup complete: Removed {total_cleaned_count} items total, freed {total_cleaned_size / (1024*1024):.1f} MB")
        else:
            logger.info(f"✅ Startup cleanup complete: No old files to clean")

    except Exception as e:
        logger.error(f"❌ Startup cleanup error: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    if client:
        client.close()
    executor.shutdown(wait=False)