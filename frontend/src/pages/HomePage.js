import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Slider } from "@/components/ui/slider";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Download, Loader2, Video, CheckCircle2, AlertCircle, Music, Settings, AudioWaveform, LogOut, Shield } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const HomePage = () => {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();

  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [videoInfo, setVideoInfo] = useState(null);
  const [selectedFormat, setSelectedFormat] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [downloadStatus, setDownloadStatus] = useState("");
  const [downloadType, setDownloadType] = useState("video"); // "video" or "audio"

  // Basic audio processing options
  const [audioOptions, setAudioOptions] = useState({
    codec: "mp3",           // mp3, m4a, opus, copy
    qscale: null,           // 0-9 for VBR (null = not used)
    bitrate: "192k",        // CBR bitrate
    channels: "stereo",     // mono, stereo
    volume: 100,            // 0-200% (100 = original)
    sampleRate: "44100"     // Hz
  });

  const handleAnalyze = async () => {
    if (!url.trim()) {
      toast.error("Vui lòng nhập URL video");
      return;
    }

    setLoading(true);
    setVideoInfo(null);
    setSelectedFormat("");

    try {
      const response = await axios.post(`${API}/analyze`, { url });
      setVideoInfo(response.data);
      toast.success("Phân tích video thành công!");
    } catch (error) {
      console.error("Analysis error:", error);
      const errorMsg = error.response?.data?.detail || "Không thể phân tích video. Vui lòng kiểm tra URL.";
      toast.error(errorMsg, { duration: 5000 });
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!selectedFormat) {
      toast.error("Vui lòng chọn chất lượng");
      return;
    }

    setDownloading(true);
    setProgress(0);
    setDownloadStatus("Đang khởi tạo...");

    try {
      // Use the downloadType state directly (no need to parse format string)
      const type = downloadType;

      // Step 1: Start download task
      setDownloadStatus("Đang bắt đầu xử lý...");

      // Build request payload
      const payload = {
        url,
        format_id: selectedFormat,
        download_type: type
      };

      // Add audio processing options if downloading audio
      if (type === "audio") {
        payload.audio_options = audioOptions;
      }

      const startResponse = await axios.post(
        `${API}/download`,
        payload,
        { timeout: 30000 }
      );

      const taskId = startResponse.data.task_id;
      console.log('Task started:', taskId);
      
      // Step 2: Poll for status
      setDownloadStatus("Đang tải và chuyển đổi video...");
      let isReady = false;
      let attempts = 0;
      const maxAttempts = 120; // 10 minutes (120 * 5s)
      
      while (!isReady && attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 5000)); // Wait 5 seconds
        attempts++;
        
        const statusResponse = await axios.get(
          `${API}/download/status/${taskId}`,
          { timeout: 10000 }
        );
        
        const status = statusResponse.data;
        console.log('Status check:', status);
        
        setProgress(status.progress || 0);
        setDownloadStatus(status.message || 'Đang xử lý...');
        
        if (status.ready) {
          isReady = true;
          break;
        }
        
        if (status.status === 'error') {
          throw new Error(status.error || 'Download failed');
        }
      }
      
      if (!isReady) {
        throw new Error('Timeout waiting for file to be ready');
      }
      
      // Step 3: Get the final status with download URL
      setDownloadStatus("File đã sẵn sàng, đang tải xuống...");
      const finalStatus = await axios.get(
        `${API}/download/status/${taskId}`,
        { timeout: 10000 }
      );
      
      const downloadUrl = finalStatus.data.download_url;
      const fileExtension = finalStatus.data.file_extension || '.mp4';
      
      if (!downloadUrl) {
        throw new Error('Download URL not available');
      }
      
      console.log('Downloading from:', `${API}${downloadUrl}`);
      console.log('File extension:', fileExtension);
      console.log('Video info:', videoInfo);
      console.log('Original title:', videoInfo?.title);
      
      // Create clean filename from video title
      const originalTitle = videoInfo?.title || 'video';
      const cleanTitle = originalTitle
        .normalize('NFD')  // Normalize Vietnamese characters
        .replace(/[\u0300-\u036f]/g, '')  // Remove diacritics
        .replace(/đ/g, 'd').replace(/Đ/g, 'D')  // Replace đ
        .replace(/[^a-zA-Z0-9\s]/g, '')  // Remove special characters
        .trim()
        .replace(/\s+/g, '_')  // Replace spaces with underscore
        .toLowerCase()
        .substring(0, 100);  // Limit length
      
      const downloadFilename = cleanTitle ? `${cleanTitle}${fileExtension}` : `video${fileExtension}`;
      
      console.log('Clean title:', cleanTitle);
      console.log('Download filename:', downloadFilename);
      
      // Step 4: Download using simple link with custom filename as query param
      const downloadUrlWithFilename = `${API}${downloadUrl}?custom_filename=${encodeURIComponent(downloadFilename)}`;
      console.log('Final download URL:', downloadUrlWithFilename);
      
      const link = document.createElement('a');
      link.href = downloadUrlWithFilename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Wait a bit to ensure download started
      await new Promise(resolve => setTimeout(resolve, 1000));

      setProgress(100);
      setDownloadStatus("Hoàn thành! File đang được tải xuống...");
      toast.success("Tải xuống thành công! Kiểm tra thư mục Downloads của bạn.");
      
      // Step 5: Cleanup backend files after a longer delay (30s to ensure download completes)
      setTimeout(async () => {
        try {
          await axios.delete(`${API}/download/cleanup/${taskId}`);
          console.log('Cleanup completed');
        } catch (err) {
          console.warn('Cleanup failed:', err);
        }
      }, 30000);  // Wait 30 seconds before cleanup
      
      setTimeout(() => {
        setDownloading(false);
        setProgress(0);
        setDownloadStatus("");
      }, 2000);
    } catch (error) {
      console.error("Download error:", error);
      
      let errorMsg = "Tải xuống thất bại. Vui lòng thử lại.";
      
      if (error.code === 'ECONNABORTED' || error.code === 'ERR_NETWORK') {
        errorMsg = "Kết nối bị gián đoạn. Vui lòng kiểm tra kết nối và thử lại.";
      } else if (error.response) {
        // Server responded with error
        errorMsg = error.response.data?.detail || `Lỗi server: ${error.response.status}`;
      } else if (error.request) {
        // Request made but no response
        errorMsg = "Không nhận được phản hồi từ server. Vui lòng kiểm tra kết nối.";
      } else if (error.message) {
        errorMsg = error.message;
      }
      
      toast.error(errorMsg, { duration: 5000 });
      setDownloading(false);
      setProgress(0);
      setDownloadStatus("");
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds) return "N/A";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto">
        {/* User Info Header */}
        <div className="flex justify-between items-center mb-6 p-4 bg-slate-800/50 border border-slate-700/50 rounded-lg backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500/10 rounded-lg border border-blue-500/20">
              <Shield className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">Đăng nhập với tư cách</p>
              <p className="font-semibold text-slate-100">
                {user?.username} {isAdmin && <span className="text-xs bg-purple-500/20 text-purple-300 px-2 py-1 rounded ml-2">Admin</span>}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            {isAdmin && (
              <Button
                onClick={() => navigate('/admin')}
                variant="outline"
                size="sm"
                className="border-purple-500/50 text-purple-300 hover:bg-purple-500/10"
              >
                <Shield className="w-4 h-4 mr-2" />
                Admin Panel
              </Button>
            )}
            <Button
              onClick={logout}
              variant="outline"
              size="sm"
              className="border-red-500/50 text-red-300 hover:bg-red-500/10"
            >
              <LogOut className="w-4 h-4 mr-2" />
              Đăng xuất
            </Button>
          </div>
        </div>

        {/* Navigation */}
        <div className="flex justify-center gap-4 mb-8">
          <Button
            variant="default"
            className="bg-blue-600 hover:bg-blue-700 text-white"
          >
            <Video className="w-4 h-4 mr-2" />
            Video Downloader
          </Button>
          <Link to="/audio-editor">
            <Button
              variant="outline"
              className="border-slate-600 text-slate-300 hover:bg-slate-800 hover:text-slate-100"
            >
              <AudioWaveform className="w-4 h-4 mr-2" />
              Audio Editor
            </Button>
          </Link>
        </div>

        {/* Header */}
        <div className="text-center mb-12" data-testid="header-section">
          <div className="flex items-center justify-center mb-6">
            <div className="p-4 bg-blue-500/10 rounded-2xl border border-blue-500/20 backdrop-blur-sm">
              <Video className="w-12 h-12 text-blue-400" />
            </div>
          </div>
          <h1 className="text-5xl sm:text-6xl font-bold mb-4 bg-gradient-to-r from-blue-400 via-cyan-400 to-blue-500 bg-clip-text text-transparent" data-testid="main-title">
            Video Downloader Pro
          </h1>
          <p className="text-lg text-slate-400 max-w-2xl mx-auto" data-testid="main-description">
            Tải video chất lượng cao từ YouTube, TikTok, Vimeo và hơn 1000+ nền tảng khác
          </p>
        </div>

        {/* URL Input Card */}
        <Card className="mb-8 bg-slate-800/50 border-slate-700/50 backdrop-blur-sm" data-testid="url-input-card">
          <CardHeader>
            <CardTitle className="text-2xl text-slate-100" data-testid="input-card-title">Nhập URL Video</CardTitle>
            <CardDescription className="text-slate-400" data-testid="input-card-description">
              Dán liên kết video bạn muốn tải xuống
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-3">
              <Input
                data-testid="url-input"
                type="text"
                placeholder="https://www.youtube.com/watch?v=..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleAnalyze()}
                className="flex-1 bg-slate-900/50 border-slate-600 text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:ring-blue-500/20"
                disabled={loading || downloading}
              />
              <Button
                data-testid="analyze-button"
                onClick={handleAnalyze}
                disabled={loading || downloading}
                className="bg-blue-600 hover:bg-blue-700 text-white px-8 transition-all duration-200 hover:scale-105"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Phân tích...
                  </>
                ) : (
                  "Phân tích"
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Video Info Card */}
        {videoInfo && (
          <Card className="mb-8 bg-slate-800/50 border-slate-700/50 backdrop-blur-sm animate-in fade-in slide-in-from-bottom-4 duration-500" data-testid="video-info-card">
            <CardContent className="p-6">
              <div className="flex gap-6 mb-6">
                {videoInfo.thumbnail && (
                  <img
                    data-testid="video-thumbnail"
                    src={videoInfo.thumbnail}
                    alt={videoInfo.title}
                    className="w-48 h-auto rounded-lg border border-slate-600 shadow-lg"
                  />
                )}
                <div className="flex-1">
                  <h3 className="text-xl font-semibold text-slate-100 mb-3" data-testid="video-title">
                    {videoInfo.title}
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="px-3 py-1 bg-blue-500/20 text-blue-300 rounded-full border border-blue-500/30" data-testid="video-source">
                        {videoInfo.source}
                      </span>
                      <span className="text-slate-400" data-testid="video-duration">
                        Thời lượng: {formatDuration(videoInfo.duration)}
                      </span>
                    </div>
                    <p className="text-slate-400" data-testid="available-formats">
                      Có sẵn {videoInfo.formats.length} định dạng chất lượng
                    </p>
                  </div>
                </div>
              </div>

              {/* Download Type Selection */}
              <div className="space-y-4">
                <label className="text-sm font-medium text-slate-300">
                  Loại tải xuống:
                </label>
                <RadioGroup
                  value={downloadType}
                  onValueChange={(value) => {
                    setDownloadType(value);
                    setSelectedFormat(""); // Reset format khi đổi type
                  }}
                  className="flex gap-6"
                >
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem value="video" id="video" className="border-slate-600 text-blue-500" />
                    <Label
                      htmlFor="video"
                      className="flex items-center gap-2 text-slate-100 cursor-pointer hover:text-blue-400 transition-colors"
                    >
                      <Video className="w-4 h-4" />
                      Video (MP4)
                    </Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem value="audio" id="audio" className="border-slate-600 text-blue-500" />
                    <Label
                      htmlFor="audio"
                      className="flex items-center gap-2 text-slate-100 cursor-pointer hover:text-blue-400 transition-colors"
                    >
                      <Music className="w-4 h-4" />
                      Audio (MP3)
                    </Label>
                  </div>
                </RadioGroup>
              </div>

              {/* Format/Quality Selection */}
              <div className="space-y-4 mt-4">
                <label className="text-sm font-medium text-slate-300" data-testid="quality-label">
                  {downloadType === "audio" ? "Chọn chất lượng audio:" : "Chọn chất lượng video:"}
                </label>
                <Select value={selectedFormat} onValueChange={setSelectedFormat}>
                  <SelectTrigger data-testid="quality-selector" className="bg-slate-900/50 border-slate-600 text-slate-100">
                    <SelectValue placeholder="Chọn chất lượng..." />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-900 border-slate-700 max-h-80">
                    {videoInfo.formats
                      .filter(format => {
                        // Filter based on download type
                        if (downloadType === "audio") {
                          return !format.has_video && format.has_audio;
                        } else {
                          return format.has_video;
                        }
                      })
                      .map((format) => (
                        <SelectItem
                          key={format.format_id}
                          value={format.format_id}
                          data-testid={`quality-option-${format.quality}`}
                          className="text-slate-100 hover:bg-slate-800 focus:bg-slate-800"
                        >
                          <div className="flex justify-between items-center w-full gap-3">
                            <span className="font-medium">{format.quality}</span>
                            <span className="text-slate-400 text-sm">
                              {format.resolution && `${format.resolution} • `}{format.filesize}
                            </span>
                          </div>
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>

                {/* Info message for audio download */}
                {downloadType === "audio" && (
                  <div className="text-xs text-slate-400 bg-slate-900/50 p-3 rounded-lg border border-slate-700/50 flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0 text-blue-400" />
                    <span>
                      Audio sẽ được tải về và xử lý bằng FFmpeg với các tùy chọn cơ bản bên dưới. Để cắt/chỉnh sửa audio nâng cao, hãy sử dụng Audio Editor sau khi tải về.
                    </span>
                  </div>
                )}
              </div>

              {/* Advanced Audio Options */}
              {downloadType === "audio" && (
                <Accordion type="single" collapsible className="w-full">
                  <AccordionItem value="audio-options" className="border-slate-700">
                    <AccordionTrigger className="text-slate-300 hover:text-slate-100">
                      <div className="flex items-center gap-2">
                        <Settings className="w-4 h-4" />
                        <span>Tùy chọn Audio nâng cao</span>
                      </div>
                    </AccordionTrigger>
                    <AccordionContent className="space-y-6 pt-4">
                      {/* Audio Codec */}
                      <div className="space-y-2">
                        <Label className="text-sm font-medium text-slate-300">Audio Codec</Label>
                        <Select
                          value={audioOptions.codec}
                          onValueChange={(value) => setAudioOptions({...audioOptions, codec: value})}
                        >
                          <SelectTrigger className="bg-slate-900/50 border-slate-600 text-slate-100">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-slate-900 border-slate-700">
                            <SelectItem value="mp3">MP3</SelectItem>
                            <SelectItem value="m4a">M4A (AAC)</SelectItem>
                            <SelectItem value="opus">Opus</SelectItem>
                            <SelectItem value="copy">Copy (Giữ nguyên codec gốc)</SelectItem>
                          </SelectContent>
                        </Select>
                        <p className="text-xs text-slate-500">Chọn định dạng audio output</p>
                      </div>

                      {/* Audio Qscale (VBR) - Only for MP3 */}
                      {audioOptions.codec === "mp3" && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <Label className="text-sm font-medium text-slate-300">
                              Audio Quality (VBR) - Qscale: {audioOptions.qscale !== null ? audioOptions.qscale : "Off"}
                            </Label>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-6 text-xs"
                              onClick={() => setAudioOptions({
                                ...audioOptions,
                                qscale: audioOptions.qscale !== null ? null : 4
                              })}
                            >
                              {audioOptions.qscale !== null ? "Tắt VBR" : "Bật VBR"}
                            </Button>
                          </div>
                          {audioOptions.qscale !== null && (
                            <>
                              <Slider
                                value={[audioOptions.qscale]}
                                onValueChange={([value]) => setAudioOptions({...audioOptions, qscale: value})}
                                min={0}
                                max={9}
                                step={1}
                                className="w-full"
                              />
                              <p className="text-xs text-slate-500">
                                0 = Chất lượng cao nhất, 9 = Thấp nhất. VBR điều chỉnh bitrate tự động.
                              </p>
                            </>
                          )}
                        </div>
                      )}

                      {/* Audio Bitrate (CBR) - Only when qscale is off */}
                      {audioOptions.codec !== "copy" && audioOptions.qscale === null && (
                        <div className="space-y-2">
                          <Label className="text-sm font-medium text-slate-300">Audio Bitrate (CBR)</Label>
                          <Select
                            value={audioOptions.bitrate}
                            onValueChange={(value) => setAudioOptions({...audioOptions, bitrate: value})}
                          >
                            <SelectTrigger className="bg-slate-900/50 border-slate-600 text-slate-100">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-900 border-slate-700">
                              <SelectItem value="64k">64 kbps</SelectItem>
                              <SelectItem value="96k">96 kbps</SelectItem>
                              <SelectItem value="128k">128 kbps</SelectItem>
                              <SelectItem value="192k">192 kbps (Khuyến nghị)</SelectItem>
                              <SelectItem value="256k">256 kbps</SelectItem>
                              <SelectItem value="320k">320 kbps (Cao nhất)</SelectItem>
                            </SelectContent>
                          </Select>
                          <p className="text-xs text-slate-500">Bitrate cố định - cao hơn = chất lượng tốt hơn</p>
                        </div>
                      )}

                      {/* Channels */}
                      {audioOptions.codec !== "copy" && (
                        <div className="space-y-2">
                          <Label className="text-sm font-medium text-slate-300">Channels</Label>
                          <RadioGroup
                            value={audioOptions.channels}
                            onValueChange={(value) => setAudioOptions({...audioOptions, channels: value})}
                            className="flex gap-4"
                          >
                            <div className="flex items-center space-x-2">
                              <RadioGroupItem value="mono" id="mono" />
                              <Label htmlFor="mono" className="cursor-pointer text-slate-300">Mono (1 kênh)</Label>
                            </div>
                            <div className="flex items-center space-x-2">
                              <RadioGroupItem value="stereo" id="stereo" />
                              <Label htmlFor="stereo" className="cursor-pointer text-slate-300">Stereo (2 kênh)</Label>
                            </div>
                          </RadioGroup>
                          <p className="text-xs text-slate-500">Số lượng kênh âm thanh</p>
                        </div>
                      )}

                      {/* Volume */}
                      {audioOptions.codec !== "copy" && (
                        <div className="space-y-2">
                          <Label className="text-sm font-medium text-slate-300">
                            Volume: {audioOptions.volume}%
                          </Label>
                          <Slider
                            value={[audioOptions.volume]}
                            onValueChange={([value]) => setAudioOptions({...audioOptions, volume: value})}
                            min={0}
                            max={200}
                            step={5}
                            className="w-full"
                          />
                          <p className="text-xs text-slate-500">
                            100% = Giữ nguyên, &lt;100% = Nhỏ hơn, &gt;100% = To hơn
                          </p>
                        </div>
                      )}

                      {/* Sample Rate */}
                      {audioOptions.codec !== "copy" && (
                        <div className="space-y-2">
                          <Label className="text-sm font-medium text-slate-300">Sample Rate (Hz)</Label>
                          <Select
                            value={audioOptions.sampleRate}
                            onValueChange={(value) => setAudioOptions({...audioOptions, sampleRate: value})}
                          >
                            <SelectTrigger className="bg-slate-900/50 border-slate-600 text-slate-100">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="bg-slate-900 border-slate-700">
                              <SelectItem value="22050">22050 Hz</SelectItem>
                              <SelectItem value="44100">44100 Hz (CD Quality)</SelectItem>
                              <SelectItem value="48000">48000 Hz (Pro Audio)</SelectItem>
                              <SelectItem value="96000">96000 Hz (Hi-Res)</SelectItem>
                            </SelectContent>
                          </Select>
                          <p className="text-xs text-slate-500">Tần số lấy mẫu âm thanh</p>
                        </div>
                      )}
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>
              )}

              {/* Download Button */}
              <Button
                data-testid="download-button"
                onClick={handleDownload}
                disabled={!selectedFormat || downloading}
                className="w-full mt-6 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700 text-white py-6 text-lg font-semibold transition-all duration-200 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
              >
                {downloading ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Đang tải xuống...
                  </>
                ) : (
                  <>
                    <Download className="w-5 h-5 mr-2" />
                    {downloadType === "audio" ? "Tải xuống MP3" : "Tải xuống Video"}
                  </>
                )}
              </Button>

              {/* Progress Bar */}
              {downloading && (
                <div className="mt-6 space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-300" data-testid="progress-section">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-slate-300 flex items-center gap-2" data-testid="download-status">
                      {progress === 100 ? (
                        <CheckCircle2 className="w-4 h-4 text-green-400" />
                      ) : (
                        <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
                      )}
                      {downloadStatus}
                    </span>
                    <span className="text-slate-400" data-testid="progress-percentage">{progress}%</span>
                  </div>
                  <Progress value={progress} className="h-2 bg-slate-700" data-testid="progress-bar" />
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Features Info */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-12" data-testid="features-section">
          <Card className="bg-slate-800/30 border-slate-700/30 backdrop-blur-sm hover:border-blue-500/30 transition-all duration-300">
            <CardContent className="p-6 text-center">
              <div className="w-12 h-12 bg-blue-500/10 rounded-xl flex items-center justify-center mx-auto mb-4">
                <Video className="w-6 h-6 text-blue-400" />
              </div>
              <h3 className="font-semibold text-slate-100 mb-2">Chất lượng cao</h3>
              <p className="text-sm text-slate-400">
                Tải video với độ phân giải tối đa có sẵn
              </p>
            </CardContent>
          </Card>
          <Card className="bg-slate-800/30 border-slate-700/30 backdrop-blur-sm hover:border-cyan-500/30 transition-all duration-300">
            <CardContent className="p-6 text-center">
              <div className="w-12 h-12 bg-cyan-500/10 rounded-xl flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 className="w-6 h-6 text-cyan-400" />
              </div>
              <h3 className="font-semibold text-slate-100 mb-2">Đa nền tảng</h3>
              <p className="text-sm text-slate-400">
                Hỗ trợ hơn 1000+ trang web video
              </p>
            </CardContent>
          </Card>
          <Card className="bg-slate-800/30 border-slate-700/30 backdrop-blur-sm hover:border-blue-500/30 transition-all duration-300">
            <CardContent className="p-6 text-center">
              <div className="w-12 h-12 bg-blue-500/10 rounded-xl flex items-center justify-center mx-auto mb-4">
                <Download className="w-6 h-6 text-blue-400" />
              </div>
              <h3 className="font-semibold text-slate-100 mb-2">Tải nhanh</h3>
              <p className="text-sm text-slate-400">
                Tốc độ tải xuống nhanh chóng và ổn định
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default HomePage;