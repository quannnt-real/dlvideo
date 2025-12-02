import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Slider } from "@/components/ui/slider";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Upload, Loader2, Download, AudioWaveform, Scissors, Play, Pause, Volume2, Video, AlertCircle, Sun, Moon } from "lucide-react";
import { ThemeToggleSimple } from "@/components/ThemeToggle";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const AudioEditor = () => {
  const [audioFile, setAudioFile] = useState(null);
  const [audioFileName, setAudioFileName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [audioId, setAudioId] = useState(null);
  const [audioDuration, setAudioDuration] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [processingProgress, setProcessingProgress] = useState(0);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef(null);
  const audioRef = useRef(null);
  const waveformRef = useRef(null);
  const wavesurferRef = useRef(null);
  const dropZoneRef = useRef(null);

  // Playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);

  // Edit options
  const [editOptions, setEditOptions] = useState({
    codec: "mp3",           // Output codec: mp3, m4a, opus, wma, flac, wav
    bitrate: "192k",        // Bitrate
    trimStart: "",          // HH:MM:SS
    trimEnd: "",            // HH:MM:SS
    enableFadeIn: false,
    fadeInDuration: 3,
    enableFadeOut: false,
    fadeOutDuration: 3,
    enableCutMiddle: false,
    cutMiddleStart: "",
    cutMiddleEnd: "",
    enableCrossfade: false,
    crossfadeDuration: 2
  });

  // Debug audioId changes
  useEffect(() => {
    console.log('🔄 audioId changed:', audioId);
  }, [audioId]);

  // Load Wavesurfer.js library
  useEffect(() => {
    const loadWavesurfer = async () => {
      if (typeof window !== 'undefined' && !window.WaveSurfer) {
        const script = document.createElement('script');
        script.src = 'https://unpkg.com/wavesurfer.js@7';
        script.async = true;
        document.body.appendChild(script);
      }
    };
    loadWavesurfer();
  }, []);

  // Initialize Wavesurfer when audio is uploaded
  useEffect(() => {
    if (audioFile && waveformRef.current && window.WaveSurfer) {
      // Destroy previous instance
      if (wavesurferRef.current) {
        wavesurferRef.current.destroy();
      }

      // Create new instance
      const wavesurfer = window.WaveSurfer.create({
        container: waveformRef.current,
        waveColor: '#60a5fa',
        progressColor: '#3b82f6',
        cursorColor: '#1e40af',
        barWidth: 2,
        barRadius: 3,
        cursorWidth: 2,
        height: 100,
        barGap: 2,
        responsive: true,
        normalize: true
      });

      // Load audio file
      const audioUrl = URL.createObjectURL(audioFile);
      wavesurfer.load(audioUrl);

      wavesurfer.on('ready', () => {
        setAudioDuration(wavesurfer.getDuration());
      });

      wavesurfer.on('audioprocess', () => {
        setCurrentTime(wavesurfer.getCurrentTime());
      });

      wavesurfer.on('play', () => setIsPlaying(true));
      wavesurfer.on('pause', () => setIsPlaying(false));
      wavesurfer.on('finish', () => setIsPlaying(false));

      wavesurferRef.current = wavesurfer;

      return () => {
        wavesurfer.destroy();
        URL.revokeObjectURL(audioUrl);
      };
    }
  }, [audioFile]);

  const uploadFile = async (file) => {
    if (!file) return;

    // Check if it's audio or video
    const isAudio = file.type.startsWith('audio/');
    const isVideo = file.type.startsWith('video/');

    if (!isAudio && !isVideo) {
      toast.error("Vui lòng chọn file audio hoặc video");
      return;
    }

    setAudioFile(file);
    setAudioFileName(file.name);
    setAudioId(null);
    setUploading(true);
    setUploadProgress(0);

    try {
      const formData = new FormData();
      formData.append('audio_file', file);

      const response = await axios.post(`${API}/audio/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        onUploadProgress: (progressEvent) => {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(progress);
        }
      });

      console.log('✅ Upload response:', response.data);
      setAudioId(response.data.audio_id);
      console.log('✅ audioId set to:', response.data.audio_id);

      if (isVideo) {
        toast.success("Upload video thành công! Audio sẽ được extract khi xử lý.");
      } else {
        toast.success("Upload audio thành công!");
      }
    } catch (error) {
      console.error("Upload error:", error);
      const errorMsg = error.response?.data?.detail || "Upload thất bại. Vui lòng thử lại.";
      toast.error(errorMsg);
      setAudioFile(null);
      setAudioFileName("");
    } finally {
      setUploading(false);
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      uploadFile(file);
    }
  };

  // Drag and drop handlers
  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      uploadFile(files[0]);
    }
  };

  const handleProcess = async () => {
    console.log('🔍 Debug - handleProcess called, audioId:', audioId);

    if (!audioId) {
      toast.error("Vui lòng upload file audio trước");
      return;
    }

    setProcessing(true);
    setProcessingProgress(0);

    try {
      // Start processing
      const response = await axios.post(`${API}/audio/process`, {
        audio_id: audioId,
        options: editOptions
      });

      const taskId = response.data.task_id;

      // Poll for status
      let isReady = false;
      let attempts = 0;
      const maxAttempts = 60; // 5 minutes

      while (!isReady && attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 5000));
        attempts++;

        const statusResponse = await axios.get(`${API}/audio/status/${taskId}`);
        const status = statusResponse.data;

        setProcessingProgress(status.progress || 0);

        if (status.ready) {
          isReady = true;
          break;
        }

        if (status.status === 'error') {
          throw new Error(status.error || 'Processing failed');
        }
      }

      if (!isReady) {
        throw new Error('Timeout waiting for processing to complete');
      }

      // Get download URL
      const finalStatus = await axios.get(`${API}/audio/status/${taskId}`);
      const downloadUrl = finalStatus.data.download_url;

      if (!downloadUrl) {
        throw new Error('Download URL not available');
      }

      // Download file - Let backend handle filename via Content-Disposition header
      const link = document.createElement('a');
      link.href = `${API}${downloadUrl}`;
      // Remove link.download to let backend set the filename
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      toast.success("Xử lý và tải xuống thành công!");

      // Cleanup immediately and reset state
      setTimeout(async () => {
        try {
          await axios.delete(`${API}/audio/cleanup/${taskId}`);
          // Reset state to allow new upload
          setAudioId(null);
          setAudioFile(null);
          setAudioFileName("");
          // Clear file input to allow re-selecting same file
          if (fileInputRef.current) {
            fileInputRef.current.value = '';
          }
          setEditOptions({
            codec: "mp3",
            bitrate: "192k",
            trimStart: "",
            trimEnd: "",
            enableFadeIn: false,
            fadeInDuration: 3,
            enableFadeOut: false,
            fadeOutDuration: 3,
            enableCutMiddle: false,
            cutMiddleStart: "",
            cutMiddleEnd: "",
            enableCrossfade: false,
            crossfadeDuration: 2
          });
          toast.info("Đã sẵn sàng để upload file mới!");
        } catch (err) {
          console.warn('Cleanup failed:', err);
        }
      }, 2000);

    } catch (error) {
      console.error("Processing error:", error);
      const errorMsg = error.response?.data?.detail || error.message || "Xử lý thất bại. Vui lòng thử lại.";
      toast.error(errorMsg);
    } finally {
      setProcessing(false);
      setProcessingProgress(0);
    }
  };

  const togglePlayPause = () => {
    if (wavesurferRef.current) {
      wavesurferRef.current.playPause();
    }
  };

  const formatTime = (seconds) => {
    if (!seconds || isNaN(seconds)) return "00:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen py-12 px-4 sm:px-6 lg:px-8 bg-background">
      <div className="max-w-4xl mx-auto">
        {/* Theme Toggle */}
        <div className="fixed top-4 right-4 z-50">
          <ThemeToggleSimple />
        </div>

        {/* Navigation */}
        <div className="flex justify-center gap-4 mb-8">
          <Link to="/">
            <Button
              variant="outline"
              className="border-border text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            >
              <Video className="w-4 h-4 mr-2" />
              Video Downloader
            </Button>
          </Link>
          <Button
            variant="default"
            className="bg-cyan-600 hover:bg-cyan-700 text-white"
          >
            <AudioWaveform className="w-4 h-4 mr-2" />
            Audio Editor
          </Button>
        </div>

        {/* Header */}
        <div className="text-center mb-12">
          <div className="flex items-center justify-center mb-6">
            <div className="p-4 bg-cyan-500/10 rounded-2xl border border-cyan-500/20 backdrop-blur-sm">
              <AudioWaveform className="w-12 h-12 text-cyan-500" />
            </div>
          </div>
          <h1 className="text-5xl sm:text-6xl font-bold mb-4 bg-gradient-to-r from-cyan-500 via-blue-500 to-cyan-600 bg-clip-text text-transparent">
            Audio Editor Pro
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Tải lên, cắt, chỉnh sửa và tải xuống audio với công cụ chuyên nghiệp
          </p>
        </div>

        {/* Upload Card */}
        <Card className="mb-8 bg-card/80 backdrop-blur-sm shadow-lg">
          <CardHeader>
            <CardTitle className="text-2xl text-card-foreground">Upload Audio/Video File</CardTitle>
            <CardDescription>
              Kéo thả file vào hoặc click để chọn. Hỗ trợ cả audio và video (sẽ tự động extract audio)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {/* Drag & Drop Zone */}
              <div
                ref={dropZoneRef}
                onDragEnter={handleDragEnter}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => !uploading && !processing && fileInputRef.current?.click()}
                className={`
                  relative border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-all duration-200
                  ${isDragging
                    ? 'border-cyan-500 bg-cyan-500/10 scale-105'
                    : 'border-border hover:border-cyan-500/50 hover:bg-accent/50'}
                  ${(uploading || processing) ? 'opacity-50 cursor-not-allowed' : ''}
                `}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="audio/*,video/*"
                  onChange={handleFileSelect}
                  className="hidden"
                  disabled={uploading || processing}
                />

                <div className="flex flex-col items-center gap-4">
                  {uploading ? (
                    <>
                      <Loader2 className="w-16 h-16 text-cyan-500 animate-spin" />
                      <div className="space-y-2 w-full max-w-md">
                        <p className="text-lg font-medium text-card-foreground">
                          Đang upload: {audioFileName}
                        </p>
                        <Progress value={uploadProgress} className="h-2" />
                        <p className="text-sm text-muted-foreground">{uploadProgress}%</p>
                      </div>
                    </>
                  ) : audioId ? (
                    <>
                      <div className="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center">
                        <AudioWaveform className="w-8 h-8 text-green-500" />
                      </div>
                      <div className="space-y-2">
                        <p className="text-lg font-medium text-green-500">✓ Upload thành công!</p>
                        <p className="text-sm text-card-foreground">{audioFileName}</p>
                        <p className="text-xs text-muted-foreground">Click để chọn file khác</p>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="w-16 h-16 rounded-full bg-cyan-500/20 flex items-center justify-center">
                        <Upload className="w-8 h-8 text-cyan-500" />
                      </div>
                      <div className="space-y-2">
                        <p className="text-lg font-medium text-card-foreground">
                          Kéo thả file vào đây
                        </p>
                        <p className="text-sm text-muted-foreground">
                          hoặc click để chọn file
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Hỗ trợ: MP3, WAV, M4A, FLAC, MP4, AVI, MOV, v.v.
                        </p>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Waveform and Editor */}
        {audioFile && (
          <Card className="mb-8 bg-card/80 backdrop-blur-sm shadow-lg animate-in fade-in slide-in-from-bottom-4 duration-500">
            <CardHeader>
              <CardTitle className="text-2xl text-card-foreground">Audio Editor</CardTitle>
              <CardDescription>
                Chỉnh sửa audio với các công cụ chuyên nghiệp
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Waveform Visualization */}
              <div className="space-y-3">
                <Label className="text-sm font-medium text-card-foreground">Waveform</Label>
                <div
                  ref={waveformRef}
                  className="bg-muted/50 rounded-lg border border-border p-4"
                />

                {/* Playback Controls */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <Button
                      size="sm"
                      onClick={togglePlayPause}
                      className="bg-cyan-600 hover:bg-cyan-700"
                    >
                      {isPlaying ? (
                        <Pause className="w-4 h-4" />
                      ) : (
                        <Play className="w-4 h-4" />
                      )}
                    </Button>
                    <span className="text-sm text-muted-foreground">
                      {formatTime(currentTime)} / {formatTime(audioDuration)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Volume2 className="w-4 h-4 text-muted-foreground" />
                  </div>
                </div>
              </div>

              {/* Output Format Settings */}
              <div className="space-y-4 pt-4 border-t border-border">
                <Label className="text-sm font-medium text-card-foreground">Định dạng Output</Label>

                <div className="grid grid-cols-2 gap-4">
                  {/* Codec Selection */}
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Audio Codec</Label>
                    <select
                      value={editOptions.codec}
                      onChange={(e) => setEditOptions({...editOptions, codec: e.target.value})}
                      className="w-full h-10 px-3 rounded-md bg-background border border-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                    >
                      <option value="mp3">MP3</option>
                      <option value="m4a">M4A (AAC)</option>
                      <option value="opus">Opus</option>
                      <option value="flac">FLAC (Lossless)</option>
                      <option value="wav">WAV (Lossless)</option>
                    </select>
                  </div>

                  {/* Bitrate Selection - Only for lossy formats */}
                  {!['flac', 'wav'].includes(editOptions.codec) && (
                    <div className="space-y-2">
                      <Label className="text-xs text-muted-foreground">Bitrate</Label>
                      <select
                        value={editOptions.bitrate}
                        onChange={(e) => setEditOptions({...editOptions, bitrate: e.target.value})}
                        className="w-full h-10 px-3 rounded-md bg-background border border-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-cyan-500"
                      >
                        <option value="96k">96 kbps</option>
                        <option value="128k">128 kbps</option>
                        <option value="192k">192 kbps (Khuyến nghị)</option>
                        <option value="256k">256 kbps</option>
                        <option value="320k">320 kbps (Cao nhất)</option>
                      </select>
                    </div>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {['flac', 'wav'].includes(editOptions.codec)
                    ? 'Format lossless - giữ nguyên chất lượng gốc'
                    : 'Chọn codec và bitrate cho file output'}
                </p>
              </div>

              {/* Trim Options */}
              <div className="space-y-4 pt-4 border-t border-border">
                <div className="flex items-center gap-2">
                  <Scissors className="w-4 h-4 text-card-foreground" />
                  <Label className="text-sm font-medium text-card-foreground">Cắt Audio (Trim)</Label>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Trim Start (HH:MM:SS)</Label>
                    <Input
                      type="text"
                      placeholder="00:00:00"
                      value={editOptions.trimStart}
                      onChange={(e) => setEditOptions({...editOptions, trimStart: e.target.value})}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">Trim End (HH:MM:SS)</Label>
                    <Input
                      type="text"
                      placeholder="00:00:00"
                      value={editOptions.trimEnd}
                      onChange={(e) => setEditOptions({...editOptions, trimEnd: e.target.value})}
                    />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">Để trống = giữ nguyên đầu/cuối</p>
              </div>

              {/* Fade Options */}
              <div className="space-y-4 pt-4 border-t border-border">
                <Label className="text-sm font-medium text-card-foreground">Hiệu ứng Fade (Mờ dần)</Label>

                {/* Fade In */}
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="enableFadeIn"
                    checked={editOptions.enableFadeIn}
                    onCheckedChange={(checked) => setEditOptions({...editOptions, enableFadeIn: checked})}
                  />
                  <div className="flex-1 space-y-2">
                    <Label htmlFor="enableFadeIn" className="text-sm text-card-foreground cursor-pointer">
                      Fade In - Âm thanh từ nhỏ đến to dần ở đầu
                    </Label>
                    {editOptions.enableFadeIn && (
                      <div className="flex items-center gap-3">
                        <Label className="text-xs text-muted-foreground whitespace-nowrap">Thời gian:</Label>
                        <Slider
                          value={[editOptions.fadeInDuration]}
                          onValueChange={([value]) => setEditOptions({...editOptions, fadeInDuration: value})}
                          min={1}
                          max={10}
                          step={0.5}
                          className="flex-1"
                        />
                        <span className="text-xs text-muted-foreground min-w-[3rem]">{editOptions.fadeInDuration}s</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Fade Out */}
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="enableFadeOut"
                    checked={editOptions.enableFadeOut}
                    onCheckedChange={(checked) => setEditOptions({...editOptions, enableFadeOut: checked})}
                  />
                  <div className="flex-1 space-y-2">
                    <Label htmlFor="enableFadeOut" className="text-sm text-card-foreground cursor-pointer">
                      Fade Out - Âm thanh từ to đến nhỏ dần ở cuối
                    </Label>
                    {editOptions.enableFadeOut && (
                      <div className="flex items-center gap-3">
                        <Label className="text-xs text-muted-foreground whitespace-nowrap">Thời gian:</Label>
                        <Slider
                          value={[editOptions.fadeOutDuration]}
                          onValueChange={([value]) => setEditOptions({...editOptions, fadeOutDuration: value})}
                          min={1}
                          max={10}
                          step={0.5}
                          className="flex-1"
                        />
                        <span className="text-xs text-muted-foreground min-w-[3rem]">{editOptions.fadeOutDuration}s</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Cut Middle Section */}
              <div className="space-y-4 pt-4 border-t border-border">
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="enableCutMiddle"
                    checked={editOptions.enableCutMiddle}
                    onCheckedChange={(checked) => setEditOptions({...editOptions, enableCutMiddle: checked})}
                  />
                  <div className="flex-1 space-y-3">
                    <Label htmlFor="enableCutMiddle" className="text-sm font-medium text-card-foreground cursor-pointer">
                      Cắt bỏ đoạn giữa
                    </Label>

                    {editOptions.enableCutMiddle && (
                      <>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="space-y-2">
                            <Label className="text-xs text-muted-foreground">Bắt đầu cắt (HH:MM:SS)</Label>
                            <Input
                              type="text"
                              placeholder="00:02:00"
                              value={editOptions.cutMiddleStart}
                              onChange={(e) => setEditOptions({...editOptions, cutMiddleStart: e.target.value})}
                              className="h-9"
                            />
                          </div>
                          <div className="space-y-2">
                            <Label className="text-xs text-muted-foreground">Kết thúc cắt (HH:MM:SS)</Label>
                            <Input
                              type="text"
                              placeholder="00:03:00"
                              value={editOptions.cutMiddleEnd}
                              onChange={(e) => setEditOptions({...editOptions, cutMiddleEnd: e.target.value})}
                              className="h-9"
                            />
                          </div>
                        </div>

                        {/* Crossfade option */}
                        <div className="flex items-start space-x-3 pl-1">
                          <Checkbox
                            id="enableCrossfade"
                            checked={editOptions.enableCrossfade}
                            onCheckedChange={(checked) => setEditOptions({...editOptions, enableCrossfade: checked})}
                          />
                          <div className="flex-1 space-y-2">
                            <Label htmlFor="enableCrossfade" className="text-xs text-card-foreground cursor-pointer">
                              Crossfade khi nối (mượt mà hơn)
                            </Label>
                            {editOptions.enableCrossfade && (
                              <div className="flex items-center gap-3">
                                <Label className="text-xs text-muted-foreground whitespace-nowrap">Thời gian:</Label>
                                <Slider
                                  value={[editOptions.crossfadeDuration]}
                                  onValueChange={([value]) => setEditOptions({...editOptions, crossfadeDuration: value})}
                                  min={0.5}
                                  max={5}
                                  step={0.5}
                                  className="flex-1"
                                />
                                <span className="text-xs text-muted-foreground min-w-[3rem]">{editOptions.crossfadeDuration}s</span>
                              </div>
                            )}
                          </div>
                        </div>

                        <div className="text-xs text-muted-foreground bg-muted/50 p-3 rounded-lg border border-border">
                          💡 Ví dụ: Bắt đầu = 00:02:00, Kết thúc = 00:03:00 → Giữ đoạn 0-2 phút và đoạn sau 3 phút, bỏ 1 phút ở giữa
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Info message if audio not uploaded yet */}
              {!audioId && (
                <div className="text-sm text-amber-600 dark:text-amber-400 bg-amber-500/10 p-3 rounded-lg border border-amber-500/30 flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <span>
                    Vui lòng upload file audio ở phía trên trước khi xử lý
                  </span>
                </div>
              )}

              {/* Process Button */}
              <Button
                onClick={() => {
                  console.log('🔘 Button clicked! audioId:', audioId, 'processing:', processing);
                  handleProcess();
                }}
                disabled={!audioId || processing}
                className="w-full bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-700 hover:to-blue-700 text-white py-6 text-lg font-semibold"
              >
                {processing ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Đang xử lý...
                  </>
                ) : (
                  <>
                    <Download className="w-5 h-5 mr-2" />
                    Xử lý và tải xuống
                  </>
                )}
              </Button>

              {/* Processing Progress */}
              {processing && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-card-foreground">Đang xử lý audio...</span>
                    <span className="text-muted-foreground">{processingProgress}%</span>
                  </div>
                  <Progress value={processingProgress} className="h-2" />
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default AudioEditor;