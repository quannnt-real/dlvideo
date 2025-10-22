import { useState } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";
import { Download, Loader2, Video, CheckCircle2, AlertCircle } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const HomePage = () => {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [videoInfo, setVideoInfo] = useState(null);
  const [selectedFormat, setSelectedFormat] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [downloadStatus, setDownloadStatus] = useState("");

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
      toast.error("Vui lòng chọn chất lượng video");
      return;
    }

    setDownloading(true);
    setProgress(0);
    setDownloadStatus("Đang khởi tạo...");

    try {
      // Create download request
      const response = await axios.post(
        `${API}/download`,
        { url, format_id: selectedFormat },
        {
          responseType: 'blob',
          onDownloadProgress: (progressEvent) => {
            if (progressEvent.total) {
              const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              setProgress(percentCompleted);
              setDownloadStatus(`Đang tải xuống... ${percentCompleted}%`);
            }
          },
        }
      );

      // Create blob and download
      const blob = new Blob([response.data], { type: 'video/mp4' });
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `${videoInfo.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.mp4`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);

      setProgress(100);
      setDownloadStatus("Hoàn thành!");
      toast.success("Tải xuống thành công!");
      
      setTimeout(() => {
        setDownloading(false);
        setProgress(0);
        setDownloadStatus("");
      }, 2000);
    } catch (error) {
      console.error("Download error:", error);
      toast.error(error.response?.data?.detail || "Tải xuống thất bại. Vui lòng thử lại.");
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

              {/* Format Selection */}
              <div className="space-y-4">
                <label className="text-sm font-medium text-slate-300" data-testid="quality-label">
                  Chọn chất lượng video:
                </label>
                <Select value={selectedFormat} onValueChange={setSelectedFormat}>
                  <SelectTrigger data-testid="quality-selector" className="bg-slate-900/50 border-slate-600 text-slate-100">
                    <SelectValue placeholder="Chọn chất lượng..." />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-900 border-slate-700">
                    {videoInfo.formats.map((format) => (
                      <SelectItem
                        key={format.format_id}
                        value={format.format_id}
                        data-testid={`quality-option-${format.quality}`}
                        className="text-slate-100 hover:bg-slate-800 focus:bg-slate-800"
                      >
                        <div className="flex justify-between items-center w-full">
                          <span className="font-medium">{format.quality}</span>
                          <span className="text-slate-400 text-sm ml-4">
                            {format.resolution} • {format.filesize}
                          </span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Button
                  data-testid="download-button"
                  onClick={handleDownload}
                  disabled={!selectedFormat || downloading}
                  className="w-full bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700 text-white py-6 text-lg font-semibold transition-all duration-200 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
                >
                  {downloading ? (
                    <>
                      <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                      Đang tải xuống...
                    </>
                  ) : (
                    <>
                      <Download className="w-5 h-5 mr-2" />
                      Tải xuống video
                    </>
                  )}
                </Button>
              </div>

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