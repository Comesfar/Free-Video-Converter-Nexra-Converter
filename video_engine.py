"""
Nexra Video Converter & Compressor - Video Engine
Handles FFmpeg execution, metadata extraction, GPU acceleration, trimming, and compression progress.
"""

import os
import re
import sys
import shutil
import tempfile
import subprocess
import threading
import time
from typing import Optional, Callable, Dict, Any, Tuple


_CACHED_GPU_ENCODERS: Optional[Dict[str, Any]] = None


def get_ffmpeg_path() -> str:
    """Finds the ffmpeg executable bundled, local, or via imageio_ffmpeg / PATH."""
    # Check PyInstaller bundle folder
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = os.path.join(meipass, "ffmpeg.exe")
        if os.path.isfile(p):
            return p

    # Check executable folder (if running as compiled exe)
    exe_dir = os.path.dirname(sys.executable)
    p = os.path.join(exe_dir, "ffmpeg.exe")
    if os.path.isfile(p):
        return p

    # Check script / project directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(script_dir, "ffmpeg.exe")
    if os.path.isfile(p):
        return p

    # Check imageio_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass

    # Check system PATH
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg

    # Common Windows paths
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    raise FileNotFoundError("FFmpeg bulunamadı! Lütfen FFmpeg'in yüklü olduğundan emin olun.")


def detect_gpu_encoders() -> Dict[str, Any]:
    """Detects available hardware video encoders (NVIDIA NVENC, AMD AMF, Intel QSV)."""
    global _CACHED_GPU_ENCODERS
    if _CACHED_GPU_ENCODERS is not None:
        return _CACHED_GPU_ENCODERS

    result = {
        "nvenc": False,
        "amf": False,
        "qsv": False,
        "recommended": "cpu",
        "description": "İşlemci (CPU)"
    }

    try:
        ffmpeg_exe = get_ffmpeg_path()
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        def test_codec(codec_name: str) -> bool:
            cmd = [
                ffmpeg_exe, "-y",
                "-f", "lavfi", "-i", "testsrc=duration=0.5:size=320x240:rate=25",
                "-c:v", codec_name,
                "-f", "null", "NUL" if sys.platform == "win32" else "/dev/null"
            ]
            p = subprocess.run(cmd, capture_output=True, startupinfo=startupinfo, timeout=5)
            return p.returncode == 0

        if test_codec("h264_nvenc"):
            result["nvenc"] = True
            result["recommended"] = "nvenc"
            result["description"] = "NVIDIA NVENC (Ultra Hızlı Donanım Hızlandırma)"
        elif test_codec("h264_amf"):
            result["amf"] = True
            result["recommended"] = "amf"
            result["description"] = "AMD AMF (Donanım Hızlandırma)"
        elif test_codec("h264_qsv"):
            result["qsv"] = True
            result["recommended"] = "qsv"
            result["description"] = "Intel QuickSync QSV (Donanım Hızlandırma)"

    except Exception as e:
        print(f"GPU detection error: {e}")

    _CACHED_GPU_ENCODERS = result
    return result


def format_seconds(seconds: float) -> str:
    """Formats float seconds into HH:MM:SS string."""
    seconds = max(0.0, seconds)
    total_s = int(seconds)
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_time_str(time_str: str) -> Optional[float]:
    """Parses HH:MM:SS or MM:SS or raw seconds into float seconds."""
    time_str = time_str.strip()
    if not time_str:
        return None

    try:
        # Check raw number
        return float(time_str.replace(",", "."))
    except ValueError:
        pass

    parts = time_str.split(":")
    try:
        if len(parts) == 3:
            h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = float(parts[0]), float(parts[1])
            return m * 60 + s
    except Exception:
        pass
    return None


def generate_thumbnail(video_path: str, timestamp_s: float, out_img_path: str) -> bool:
    """Extracts a single frame from video at timestamp_s and saves as JPEG."""
    try:
        ffmpeg_exe = get_ffmpeg_path()
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        time_str = format_seconds(timestamp_s)
        cmd = [
            ffmpeg_exe, "-y",
            "-ss", time_str,
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "3",
            out_img_path
        ]
        res = subprocess.run(cmd, capture_output=True, startupinfo=startupinfo, timeout=10)
        return (res.returncode == 0) and os.path.isfile(out_img_path)
    except Exception:
        return False


class VideoMetadata:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.filesize_bytes = os.path.getsize(filepath) if os.path.isfile(filepath) else 0
        self.filesize_mb = self.filesize_bytes / (1024 * 1024)
        self.duration_seconds = 0.0
        self.duration_formatted = "00:00"
        self.width = 0
        self.height = 0
        self.fps = 0.0
        self.video_codec = "Bilinmiyor"
        self.has_audio = False
        self.audio_codec = "Yok"
        self.audio_bitrate_kbps = 0
        self.total_bitrate_kbps = 0
        self.is_valid = False
        self.error_message = ""

        self._extract_metadata()

    def _extract_metadata(self):
        try:
            ffmpeg_exe = get_ffmpeg_path()
            cmd = [ffmpeg_exe, "-hide_banner", "-i", self.filepath]
            
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                startupinfo=startupinfo,
                timeout=15
            )
            err = res.stderr

            # Parse Duration
            dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
            if dur_match:
                h = float(dur_match.group(1))
                m = float(dur_match.group(2))
                s = float(dur_match.group(3))
                self.duration_seconds = h * 3600 + m * 60 + s
                self.duration_formatted = format_seconds(self.duration_seconds)

            # Parse Total Bitrate
            br_match = re.search(r"bitrate:\s*(\d+)\s*kb/s", err)
            if br_match:
                self.total_bitrate_kbps = int(br_match.group(1))

            # Parse Video Stream
            vid_match = re.search(r"Stream #\d+:\d+.*Video:\s*([a-zA-Z0-9_\-]+)", err)
            if vid_match:
                self.video_codec = vid_match.group(1)

            res_match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
            if res_match:
                self.width = int(res_match.group(1))
                self.height = int(res_match.group(2))

            fps_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:fps|tbr)", err)
            if fps_match:
                self.fps = float(fps_match.group(1))

            # Parse Audio Stream
            aud_match = re.search(r"Stream #\d+:\d+.*Audio:\s*([a-zA-Z0-9_\-]+)", err)
            if aud_match:
                self.has_audio = True
                self.audio_codec = aud_match.group(1)
                abr_match = re.search(r"Audio:.*?(\d+)\s*kb/s", err)
                if abr_match:
                    self.audio_bitrate_kbps = int(abr_match.group(1))
                else:
                    self.audio_bitrate_kbps = 128

            if self.duration_seconds > 0:
                self.is_valid = True
            else:
                self.error_message = "Video süresi tespit edilemedi veya geçersiz video dosyası."
        except Exception as e:
            self.is_valid = False
            self.error_message = str(e)


def calculate_bitrates(
    duration_sec: float,
    target_mb: float,
    has_audio: bool,
    audio_mode: str = "auto"
) -> Dict[str, Any]:
    """
    Calculates the exact video and audio bitrate in kbps needed to hit target_mb.
    Includes container overhead buffer (4%) to ensure the file never exceeds the target.
    """
    if duration_sec <= 0:
        return {"video_kbps": 1000, "audio_kbps": 128, "total_kbps": 1128, "warning": "Geçersiz süre"}

    # Target size in bits with a 4% safety margin for MP4/MKV muxing overhead
    safety_factor = 0.96
    target_bytes = target_mb * 1024 * 1024
    usable_bits = target_bytes * safety_factor * 8
    total_bitrate_kbps = usable_bits / duration_sec / 1000.0

    warning = ""
    if total_bitrate_kbps < 120:
        warning = "Hedef boyut video süresine göre çok küçük! Görüntü kalitesi düşük olabilir veya çözünürlük 480p/360p yapılmalıdır."

    # Determine audio bitrate
    if not has_audio or audio_mode == "mute":
        audio_kbps = 0
    elif audio_mode == "128k":
        audio_kbps = 128
    elif audio_mode == "96k":
        audio_kbps = 96
    elif audio_mode == "64k":
        audio_kbps = 64
    else:  # auto
        if total_bitrate_kbps < 350:
            audio_kbps = 48
        elif total_bitrate_kbps < 700:
            audio_kbps = 64
        elif total_bitrate_kbps < 1500:
            audio_kbps = 96
        else:
            audio_kbps = 128

    if audio_kbps > 0 and total_bitrate_kbps > 80:
        max_allowed_audio = max(32, int(total_bitrate_kbps * 0.25))
        if audio_kbps > max_allowed_audio:
            audio_kbps = max_allowed_audio

    video_kbps = max(50, int(total_bitrate_kbps - audio_kbps))

    return {
        "video_kbps": video_kbps,
        "audio_kbps": audio_kbps,
        "total_kbps": int(total_bitrate_kbps),
        "warning": warning
    }


def get_recommended_resolution(video_kbps: int, original_w: int, original_h: int) -> str:
    """Returns recommended resolution string based on available video bitrate."""
    max_dim = max(original_w, original_h)
    if video_kbps < 350:
        return "480p" if max_dim > 640 else "original"
    elif video_kbps < 850:
        return "720p" if max_dim > 1280 else "original"
    elif video_kbps < 2200:
        return "1080p" if max_dim > 1920 else "original"
    return "original"


class CompressionJob:
    """Handles running ffmpeg compression with GPU acceleration, trimming, and real-time progress callbacks."""

    def __init__(
        self,
        input_path: str,
        output_path: str,
        target_mb: float,
        resolution_mode: str = "auto",  # 'auto', 'original', '1080p', '720p', '480p', '360p'
        codec: str = "h264",            # 'h264' or 'hevc'
        mode: str = "2pass",            # '2pass' or '1pass'
        audio_mode: str = "auto",        # 'auto', '128k', '96k', '64k', 'mute'
        speed_preset: str = "medium",   # 'fast', 'medium', 'slow'
        hardware_accel: str = "auto",   # 'auto', 'nvenc', 'cpu'
        trim_start: Optional[float] = None,
        trim_end: Optional[float] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_complete: Optional[Callable[[bool, str, Dict[str, Any]], None]] = None
    ):
        self.input_path = input_path
        self.output_path = output_path
        self.target_mb = target_mb
        self.resolution_mode = resolution_mode
        self.codec = codec
        self.mode = mode
        self.audio_mode = audio_mode
        self.speed_preset = speed_preset
        self.hardware_accel = hardware_accel
        self.trim_start = trim_start
        self.trim_end = trim_end
        self.on_progress = on_progress
        self.on_complete = on_complete

        self._cancelled = False
        self._current_proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._cancelled = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancelled = True
        if self._current_proc:
            try:
                self._current_proc.terminate()
                time.sleep(0.2)
                if self._current_proc.poll() is None:
                    self._current_proc.kill()
            except Exception:
                pass

    def _build_scale_filter(self, meta: VideoMetadata, effective_duration: float) -> Optional[str]:
        target_res = self.resolution_mode
        if target_res == "auto":
            bitrates = calculate_bitrates(effective_duration, self.target_mb, meta.has_audio, self.audio_mode)
            rec = get_recommended_resolution(bitrates["video_kbps"], meta.width, meta.height)
            if rec == "original":
                target_res = "original"
            else:
                target_res = rec

        if target_res == "original" or meta.width == 0 or meta.height == 0:
            return None

        res_map = {
            "1080p": (1920, 1080),
            "720p": (1280, 720),
            "480p": (854, 480),
            "360p": (640, 360),
        }
        if target_res not in res_map:
            return None

        target_w, target_h = res_map[target_res]
        is_landscape = meta.width >= meta.height

        if is_landscape:
            if meta.height <= target_h:
                return None
            return f"scale=-2:min({target_h}\\,ih)"
        else:
            if meta.width <= target_h:
                return None
            return f"scale=min({target_h}\\,iw):-2"

    def _determine_encoder(self) -> Tuple[str, bool]:
        """Returns (encoder_name, is_gpu)."""
        gpus = detect_gpu_encoders()
        accel = self.hardware_accel

        if accel == "auto":
            if gpus["nvenc"]:
                accel = "nvenc"
            else:
                accel = "cpu"

        if accel == "nvenc" and gpus["nvenc"]:
            return ("h264_nvenc" if self.codec == "h264" else "hevc_nvenc", True)
        
        # Fallback to CPU
        return ("libx264" if self.codec == "h264" else "libx265", False)

    def _run(self):
        ffmpeg_exe = get_ffmpeg_path()
        meta = VideoMetadata(self.input_path)

        if not meta.is_valid:
            if self.on_complete:
                self.on_complete(False, f"Hata: {meta.error_message}", {})
            return

        # Handle Trimming duration
        total_duration = meta.duration_seconds
        has_trim = False
        trim_args = []
        if self.trim_start is not None and self.trim_end is not None and (self.trim_end > self.trim_start):
            has_trim = True
            effective_duration = self.trim_end - self.trim_start
            trim_args = ["-ss", format_seconds(self.trim_start), "-to", format_seconds(self.trim_end)]
        else:
            effective_duration = total_duration

        effective_duration = max(1.0, effective_duration)

        bitrates = calculate_bitrates(
            effective_duration,
            self.target_mb,
            meta.has_audio,
            self.audio_mode
        )
        video_kbps = bitrates["video_kbps"]
        audio_kbps = bitrates["audio_kbps"]

        # Codec / Hardware Selection
        vcodec, is_gpu = self._determine_encoder()

        # Scale filter
        scale_filter = self._build_scale_filter(meta, effective_duration)
        vf_args = []
        if scale_filter:
            vf_args = ["-vf", scale_filter]

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        start_time = time.time()
        temp_dir = tempfile.mkdtemp(prefix="nexra_")
        pass_log = os.path.join(temp_dir, "passlog").replace("\\", "/")

        try:
            # Common audio parameters
            audio_args = []
            if audio_kbps > 0 and meta.has_audio and self.audio_mode != "mute":
                audio_args = ["-c:a", "aac", "-b:a", f"{audio_kbps}k"]
            else:
                audio_args = ["-an"]

            # Web streaming optimization
            faststart_args = ["-movflags", "+faststart"] if self.output_path.lower().endswith(".mp4") else []

            # =========================================================
            # GPU ACCELERATED ENCODING (NVENC)
            # =========================================================
            if is_gpu:
                # NVENC hardware multipass handles 2-pass analysis in hardware at 500+ FPS
                gpu_cmd = [
                    ffmpeg_exe, "-y",
                    *trim_args,
                    "-i", self.input_path,
                    "-c:v", vcodec,
                    "-multipass", "fullres",
                    "-rc:v", "vbr",
                    "-b:v", f"{video_kbps}k",
                    "-maxrate:v", f"{int(video_kbps * 1.25)}k",
                    "-bufsize:v", f"{int(video_kbps * 2)}k",
                    "-pix_fmt", "yuv420p",
                    *vf_args,
                    *audio_args,
                    *faststart_args,
                    "-progress", "pipe:1",
                    self.output_path
                ]

                ok, err_msg = self._execute_ffmpeg_pass(
                    gpu_cmd, effective_duration, 0.0, 1.0, "⚡ GPU (NVENC) ile Sıkıştırılıyor...", startupinfo, start_time
                )
                if not ok:
                    if self._cancelled:
                        self._cleanup_temp(temp_dir, self.output_path)
                        if self.on_complete:
                            self.on_complete(False, "İşlem kullanıcı tarafından iptal edildi.", {})
                        return
                    raise RuntimeError(f"GPU Kodlama hatası: {err_msg}")

            # =========================================================
            # CPU ENCODING (libx264 / libx265)
            # =========================================================
            elif self.mode == "2pass":
                # PASS 1
                pass1_cmd = [
                    ffmpeg_exe, "-y",
                    *trim_args,
                    "-i", self.input_path,
                    "-c:v", vcodec,
                    "-b:v", f"{video_kbps}k",
                    "-pass", "1",
                    "-passlogfile", pass_log,
                    "-preset", self.speed_preset,
                    "-pix_fmt", "yuv420p",
                    "-an",
                    *vf_args,
                    "-f", "null",
                    "-progress", "pipe:1",
                    "NUL" if sys.platform == "win32" else "/dev/null"
                ]

                ok1, err1 = self._execute_ffmpeg_pass(
                    pass1_cmd, effective_duration, 0.0, 0.45, "1. Geçiş Analiz Ediliyor...", startupinfo, start_time
                )
                if not ok1:
                    if self._cancelled:
                        self._cleanup_temp(temp_dir, self.output_path)
                        if self.on_complete:
                            self.on_complete(False, "İşlem kullanıcı tarafından iptal edildi.", {})
                        return
                    raise RuntimeError(f"1. Geçiş hatası: {err1}")

                if self._cancelled:
                    self._cleanup_temp(temp_dir, self.output_path)
                    if self.on_complete:
                        self.on_complete(False, "İşlem iptal edildi.", {})
                    return

                # PASS 2
                pass2_cmd = [
                    ffmpeg_exe, "-y",
                    *trim_args,
                    "-i", self.input_path,
                    "-c:v", vcodec,
                    "-b:v", f"{video_kbps}k",
                    "-pass", "2",
                    "-passlogfile", pass_log,
                    "-preset", self.speed_preset,
                    "-pix_fmt", "yuv420p",
                    *vf_args,
                    *audio_args,
                    *faststart_args,
                    "-progress", "pipe:1",
                    self.output_path
                ]

                ok2, err2 = self._execute_ffmpeg_pass(
                    pass2_cmd, effective_duration, 0.45, 1.0, "2. Geçiş Sıkıştırılıyor...", startupinfo, start_time
                )
                if not ok2:
                    if self._cancelled:
                        self._cleanup_temp(temp_dir, self.output_path)
                        if self.on_complete:
                            self.on_complete(False, "İşlem kullanıcı tarafından iptal edildi.", {})
                        return
                    raise RuntimeError(f"2. Geçiş hatası: {err2}")

            else:
                # 1-PASS CPU
                cmd = [
                    ffmpeg_exe, "-y",
                    *trim_args,
                    "-i", self.input_path,
                    "-c:v", vcodec,
                    "-b:v", f"{video_kbps}k",
                    "-maxrate", f"{int(video_kbps * 1.3)}k",
                    "-bufsize", f"{int(video_kbps * 2)}k",
                    "-preset", self.speed_preset,
                    "-pix_fmt", "yuv420p",
                    *vf_args,
                    *audio_args,
                    *faststart_args,
                    "-progress", "pipe:1",
                    self.output_path
                ]

                ok, err_msg = self._execute_ffmpeg_pass(
                    cmd, effective_duration, 0.0, 1.0, "Sıkıştırılıyor...", startupinfo, start_time
                )
                if not ok:
                    if self._cancelled:
                        self._cleanup_temp(temp_dir, self.output_path)
                        if self.on_complete:
                            self.on_complete(False, "İşlem kullanıcı tarafından iptal edildi.", {})
                        return
                    raise RuntimeError(f"Sıkıştırma hatası: {err_msg}")

            # Finished successfully!
            if os.path.isfile(self.output_path) and os.path.getsize(self.output_path) > 0:
                final_bytes = os.path.getsize(self.output_path)
                final_mb = final_bytes / (1024 * 1024)
                orig_comparable_bytes = meta.filesize_bytes * (effective_duration / total_duration) if total_duration > 0 else meta.filesize_bytes
                savings_pct = (1.0 - (final_bytes / orig_comparable_bytes)) * 100 if orig_comparable_bytes > 0 else 0
                elapsed = time.time() - start_time

                summary = {
                    "original_mb": round(meta.filesize_mb, 2),
                    "final_mb": round(final_mb, 2),
                    "target_mb": round(self.target_mb, 2),
                    "savings_pct": round(savings_pct, 1),
                    "elapsed_sec": round(elapsed, 1),
                    "output_path": self.output_path,
                    "resolution": f"{meta.width}x{meta.height}",
                    "codec": ("GPU " + vcodec.upper()) if is_gpu else self.codec.upper(),
                    "trimmed": has_trim,
                    "duration": format_seconds(effective_duration)
                }
                if self.on_complete:
                    self.on_complete(True, "Sıkıştırma başarıyla tamamlandı!", summary)
            else:
                if self.on_complete:
                    self.on_complete(False, "Çıktı dosyası oluşturulamadı.", {})

        except Exception as e:
            if self.on_complete:
                self.on_complete(False, f"Hata: {str(e)}", {})
        finally:
            self._cleanup_temp(temp_dir, None)

    def _execute_ffmpeg_pass(
        self,
        cmd: list,
        total_duration_s: float,
        start_ratio: float,
        end_ratio: float,
        phase_label: str,
        startupinfo,
        overall_start_time: float
    ) -> Tuple[bool, str]:
        """Runs ffmpeg and reads -progress stdout lines to report progress."""
        stderr_buffer = []
        try:
            self._current_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                startupinfo=startupinfo,
                encoding="utf-8",
                errors="ignore"
            )

            def read_stderr():
                for line in self._current_proc.stderr:
                    if len(stderr_buffer) < 40:
                        stderr_buffer.append(line)

            t_err = threading.Thread(target=read_stderr, daemon=True)
            t_err.start()

            total_us = total_duration_s * 1000000.0
            ratio_span = end_ratio - start_ratio
            last_report_time = 0

            for line in self._current_proc.stdout:
                if self._cancelled:
                    self._current_proc.kill()
                    return False, "İptal edildi"

                line = line.strip()
                if line.startswith("out_time_us="):
                    val_str = line.split("=")[1]
                    try:
                        curr_us = float(val_str)
                        curr_ratio = min(1.0, max(0.0, curr_us / total_us)) if total_us > 0 else 0
                        overall_pct = (start_ratio + curr_ratio * ratio_span) * 100.0

                        now = time.time()
                        if now - last_report_time >= 0.12:
                            last_report_time = now
                            elapsed = now - overall_start_time
                            if overall_pct > 1.0:
                                eta_sec = max(0, int((elapsed / (overall_pct / 100.0)) - elapsed))
                                eta_text = f"{eta_sec // 60:02d}:{eta_sec % 60:02d}"
                            else:
                                eta_text = "--:--"

                            if self.on_progress:
                                self.on_progress({
                                    "percent": round(overall_pct, 1),
                                    "phase": phase_label,
                                    "phase_percent": round(curr_ratio * 100.0, 1),
                                    "elapsed": f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}",
                                    "eta": eta_text
                                })
                    except ValueError:
                        pass
                elif line == "progress=end":
                    if self.on_progress:
                        self.on_progress({
                            "percent": round(end_ratio * 100.0, 1),
                            "phase": phase_label,
                            "phase_percent": 100.0,
                            "elapsed": "--:--",
                            "eta": "00:00"
                        })

            self._current_proc.wait()
            t_err.join(timeout=1.0)
            if self._current_proc.returncode != 0 and not self._cancelled:
                return False, "".join(stderr_buffer[-5:])
            return ((self._current_proc.returncode == 0) and not self._cancelled), ""
        except Exception as e:
            if not self._cancelled:
                return False, str(e)
            return False, "İptal edildi"

    def _cleanup_temp(self, temp_dir: str, target_file_to_remove: Optional[str] = None):
        try:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            if self._cancelled and target_file_to_remove and os.path.exists(target_file_to_remove):
                os.remove(target_file_to_remove)
        except Exception:
            pass
