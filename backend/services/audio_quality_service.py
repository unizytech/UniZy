"""
Audio Quality Service - Comprehensive audio quality analysis for transcription readiness.

Analyzes uploaded and recorded audio for:
- Signal-to-Noise Ratio (SNR)
- Volume levels (RMS and peak)
- Clipping detection
- Silence ratio
- Speech presence detection
- Duration validation

This service runs async and does NOT block the transcription/extraction pipeline.
"""

import numpy as np
import io
import base64
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import audio processing libraries
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    logger.warning("librosa not available - audio quality analysis will be limited")

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("pydub not available - audio format conversion may fail")


# Quality thresholds
THRESHOLDS = {
    "snr_good": 20,        # dB - above this is good
    "snr_fair": 10,        # dB - above this is fair, below is poor
    "rms_too_quiet": -35,  # dB - below this is too quiet
    "rms_very_quiet": -40, # dB - below this is critically quiet
    "clipping_warn": 0.01, # 1% of samples clipped
    "silence_high": 0.70,  # 70% silence is concerning
    "speech_min": 0.10,    # At least 10% of frames should have speech
    "duration_min": 3.0,   # seconds - minimum useful duration
    "duration_max": 1800,  # 30 minutes - warn if very long
}

# Sampling thresholds for long recordings (reduces analysis time)
SAMPLE_THRESHOLD_SECONDS = 120  # 2 minutes - sample if longer
SAMPLE_DURATION_SECONDS = 30    # Sample first and last 30 seconds


def analyze_audio_quality(
    audio_base64: str,
    mime_type: str,
    known_duration_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Comprehensive audio quality analysis for transcription readiness.

    Args:
        audio_base64: Base64-encoded audio data
        mime_type: MIME type of the audio (e.g., 'audio/webm', 'audio/wav')

    Returns:
        {
            "overall_quality": str,      # "good", "fair", "poor"
            "is_acceptable": bool,       # True if quality >= fair
            "issues": [                  # List of detected issues
                {
                    "type": str,         # "low_snr", "too_quiet", "clipping", etc.
                    "severity": str,     # "warning", "critical"
                    "message": str       # Human-readable description
                }
            ],
            "metrics": {
                "snr_db": float,         # Signal-to-noise ratio
                "rms_db": float,         # Overall volume level
                "peak_db": float,        # Peak amplitude
                "clipping_ratio": float, # % of clipped samples
                "silence_ratio": float,  # % of silent frames
                "speech_detected": bool, # Voice activity present
                "duration_seconds": float
            },
            "summary_message": str       # Combined warning message for UI
        }
    """
    if not LIBROSA_AVAILABLE:
        logger.warning("librosa not available, returning default quality result")
        return _get_default_result("librosa not installed")

    try:
        # Decode base64 once — reused by the fast container probe and the full pydub decode.
        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as e:
            logger.error(f"[QUALITY] base64 decode failed: {e}")
            return _get_default_result("Invalid base64 audio")

        # Fast container probe: short-circuit pydub decode only when ffprobe
        # genuinely cannot read the container, or reports a pathologically short
        # duration (the original 28MB / 0.04s corruption case). When ffprobe
        # parses the container but duration is missing — common for
        # MediaRecorder streaming WebM — fall through to full pydub analysis.
        if len(audio_bytes) >= 100_000:
            probe_dur = fast_container_duration_seconds(audio_bytes, mime_type)
            if probe_dur is None:
                logger.warning(
                    f"[QUALITY] ffprobe could not parse "
                    f"{len(audio_bytes) // 1024}KB file ({mime_type}). "
                    f"Skipping pydub decode."
                )
                return _get_default_result("Audio container unparseable")
            # PROBE_PARSEABLE_NO_DURATION is < 0; only flag genuine corruption
            # when ffprobe gave us a real (positive) duration that's tiny.
            if 0.0 <= probe_dur < 1.0:
                logger.warning(
                    f"[QUALITY] Container reports only {probe_dur:.2f}s for a "
                    f"{len(audio_bytes) / 1024 / 1024:.1f}MB file — skipping pydub decode."
                )
                return _get_default_result(
                    f"Audio container corrupted (decodes to {probe_dur:.2f}s)",
                    duration_seconds=probe_dur,
                )

        # Decode and convert audio
        audio_data, sample_rate = _decode_audio(audio_bytes, mime_type)

        if audio_data is None:
            return _get_default_result("Failed to decode audio")

        # Store original duration before sampling
        original_duration = len(audio_data) / sample_rate

        # MediaRecorder streaming WebM fallback: when chunks 1+ are concatenated
        # without their EBML init segment, pydub often decodes only the header-
        # bearing first chunk and reports a sub-second duration for what is
        # actually minutes of audio. Trust the caller's chunk-derived duration
        # when the decoded value is implausibly short for the input bytes.
        if (
            known_duration_seconds is not None
            and known_duration_seconds > 0
            and original_duration < 1.0
            and len(audio_bytes) > 100_000
        ):
            logger.warning(
                f"[QUALITY] Decoded duration {original_duration:.3f}s implausibly "
                f"short for {len(audio_bytes) // 1024}KB audio; using caller-"
                f"provided duration {known_duration_seconds:.1f}s"
            )
            original_duration = float(known_duration_seconds)

        # ============================================================================
        # OPTIMIZATION: Sample first/last 30s for long recordings (>2 min)
        # This reduces analysis time from ~5s to ~0.5s for 10-minute recordings
        # while still capturing representative audio quality
        # ============================================================================
        if original_duration > SAMPLE_THRESHOLD_SECONDS:
            sample_length = int(SAMPLE_DURATION_SECONDS * sample_rate)

            # First 30 seconds
            first_sample = audio_data[:sample_length]
            # Last 30 seconds
            last_sample = audio_data[-sample_length:]
            # Combine samples
            audio_data = np.concatenate([first_sample, last_sample])

            logger.info(
                f"[QUALITY] Long recording ({original_duration:.1f}s) - "
                f"sampling first/last {SAMPLE_DURATION_SECONDS}s for quality analysis"
            )

        # Calculate all metrics (on possibly sampled audio)
        metrics = _calculate_metrics(audio_data, sample_rate)

        # Restore original duration in metrics (important for downstream logic)
        metrics["duration_seconds"] = original_duration

        # Classify quality based on metrics
        overall_quality, issues = _classify_quality(metrics)

        # Generate summary message
        summary_message = _generate_summary(overall_quality, issues)

        result = {
            "overall_quality": overall_quality,
            "is_acceptable": overall_quality in ("good", "fair"),
            "issues": issues,
            "metrics": metrics,
            "summary_message": summary_message
        }

        logger.info(f"[QUALITY] Analysis complete: {overall_quality}, SNR: {metrics['snr_db']:.1f}dB, "
                   f"RMS: {metrics['rms_db']:.1f}dB, Duration: {metrics['duration_seconds']:.1f}s")

        return result

    except Exception as e:
        logger.error(f"[QUALITY] Analysis failed: {e}")
        return _get_default_result(f"Analysis error: {str(e)}")


def _decode_audio(audio_bytes: bytes, mime_type: str) -> Tuple[np.ndarray, int]:
    """
    Decode raw audio bytes to numpy array.

    Returns:
        Tuple of (audio_data as numpy array, sample_rate)
    """
    try:
        # Use pydub to convert any format to wav, then load with librosa
        if PYDUB_AVAILABLE:
            # Determine format from mime type (comprehensive mapping)
            format_map = {
                # WebM
                'audio/webm': 'webm',
                'video/webm': 'webm',
                # MP3
                'audio/mp3': 'mp3',
                'audio/mpeg': 'mp3',
                'audio/mpeg3': 'mp3',
                'audio/x-mpeg-3': 'mp3',
                # WAV
                'audio/wav': 'wav',
                'audio/x-wav': 'wav',
                'audio/wave': 'wav',
                'audio/vnd.wave': 'wav',
                # OGG
                'audio/ogg': 'ogg',
                'application/ogg': 'ogg',
                'audio/vorbis': 'ogg',
                # FLAC
                'audio/flac': 'flac',
                'audio/x-flac': 'flac',
                # M4A/AAC/MP4
                'audio/m4a': 'm4a',
                'audio/x-m4a': 'm4a',
                'audio/mp4': 'm4a',
                'audio/x-mp4': 'm4a',
                'audio/aac': 'aac',
                'audio/aacp': 'aac',
                'audio/x-aac': 'aac',
                'video/mp4': 'mp4',
                'application/mp4': 'mp4',
                # 3GP
                'audio/3gpp': '3gp',
                'video/3gpp': '3gp',
                'audio/3gpp2': '3gp',
            }

            mime_lower = mime_type.lower() if mime_type else ''
            audio_format = format_map.get(mime_lower)

            # Log the mime type for debugging
            logger.info(f"[QUALITY] Decoding audio - mime_type: {mime_type}, detected_format: {audio_format}")

            # Try with detected format first, then fallback to auto-detection
            formats_to_try = []
            if audio_format:
                formats_to_try.append(audio_format)

            # Add common formats as fallbacks for auto-detection
            # Order matters: try most common formats first
            fallback_formats = ['m4a', 'mp4', 'mp3', 'wav', 'ogg', 'webm', 'aac', 'flac']
            for fmt in fallback_formats:
                if fmt not in formats_to_try:
                    formats_to_try.append(fmt)

            last_error = None
            for fmt in formats_to_try:
                try:
                    audio_segment = AudioSegment.from_file(
                        io.BytesIO(audio_bytes),
                        format=fmt
                    )

                    # Convert to mono and get raw samples
                    audio_segment = audio_segment.set_channels(1)
                    sample_rate = audio_segment.frame_rate

                    # Get samples as numpy array, normalized to [-1, 1]
                    samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
                    samples = samples / (2 ** (audio_segment.sample_width * 8 - 1))

                    if fmt != audio_format:
                        logger.info(f"[QUALITY] Successfully decoded with fallback format: {fmt}")

                    return samples, sample_rate
                except Exception as e:
                    last_error = e
                    continue

            # All formats failed
            logger.error(f"[QUALITY] All format attempts failed. Last error: {last_error}")
            return None, None
        else:
            # Try direct librosa loading (works for some formats)
            audio_data, sr = librosa.load(io.BytesIO(audio_bytes), sr=None, mono=True)
            return audio_data, sr

    except Exception as e:
        logger.error(f"[QUALITY] Audio decode failed: {e}")
        return None, None


# Sentinel returned by fast_container_duration_seconds when ffprobe successfully
# parsed the container but the duration is not stored in metadata. Common with
# MediaRecorder-produced streaming WebM, where the EBML duration field is left
# empty because the recorder doesn't seek back to write it. This is NOT a
# corruption signal — the audio is fully decodable.
PROBE_PARSEABLE_NO_DURATION = -1.0


def fast_container_duration_seconds(audio_bytes: bytes, mime_type: str) -> Optional[float]:
    """
    Container-only duration check via ffprobe — no full decode.

    Returns one of three signals:
      - positive float: duration in seconds (container parseable, duration in metadata)
      - PROBE_PARSEABLE_NO_DURATION (-1.0): container parseable, duration missing
        (common for MediaRecorder streaming WebM)
      - None: ffprobe unavailable or container truly unparseable

    Callers must distinguish PROBE_PARSEABLE_NO_DURATION from None — only the
    latter signals corruption.

    Typical cost: <100ms even for a 30MB WebM, vs. multi-second full pydub decode.
    """
    import subprocess
    import tempfile
    import os
    import shutil

    if not shutil.which("ffprobe"):
        return None

    ext_map = {
        "audio/webm": ".webm", "video/webm": ".webm",
        "audio/mp3": ".mp3",   "audio/mpeg": ".mp3",
        "audio/wav": ".wav",   "audio/x-wav": ".wav",
        "audio/m4a": ".m4a",   "audio/x-m4a": ".m4a",
        "audio/mp4": ".m4a",   "video/mp4": ".mp4",
        "audio/ogg": ".ogg",   "audio/flac": ".flac",
        "audio/aac": ".aac",   "audio/3gpp": ".3gp",
    }
    ext = ext_map.get((mime_type or "").lower(), ".bin")

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tmp.write(audio_bytes)
        tmp.close()
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", tmp.name],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        out = (result.stdout or "").strip()
        # ffprobe parsed the container (returncode 0) but the duration field
        # is absent. This is the MediaRecorder streaming-WebM case — treat
        # as parseable, not as failure.
        if not out or out.upper() == "N/A":
            return PROBE_PARSEABLE_NO_DURATION
        try:
            return float(out)
        except ValueError:
            # ffprobe returncode said parseable but the duration string is
            # something we can't read. Conservatively treat as parseable
            # without duration rather than as a failure.
            return PROBE_PARSEABLE_NO_DURATION
    except Exception as e:
        logger.debug(f"[QUALITY] fast_container_duration_seconds failed: {e}")
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _calculate_metrics(audio_data: np.ndarray, sr: int) -> Dict[str, Any]:
    """Calculate all audio quality metrics."""

    # Duration
    duration = len(audio_data) / sr

    # Ensure we have valid audio data
    if len(audio_data) == 0:
        return {
            "snr_db": 0.0,
            "rms_db": -60.0,
            "peak_db": -60.0,
            "clipping_ratio": 0.0,
            "silence_ratio": 1.0,
            "speech_detected": False,
            "duration_seconds": 0.0
        }

    # RMS (volume level)
    rms = np.sqrt(np.mean(audio_data ** 2))
    rms_db = 20 * np.log10(rms + 1e-10)

    # Peak level
    peak = np.max(np.abs(audio_data))
    peak_db = 20 * np.log10(peak + 1e-10)

    # Clipping detection (samples at >99% of max possible amplitude)
    # For normalized audio, max is 1.0
    clipped_samples = np.sum(np.abs(audio_data) > 0.99)
    clipping_ratio = clipped_samples / len(audio_data)

    # Frame-based analysis for silence and speech detection
    frame_length = int(sr * 0.025)  # 25ms frames
    hop_length = int(sr * 0.010)    # 10ms hop

    # Compute RMS per frame
    rms_frames = librosa.feature.rms(y=audio_data, frame_length=frame_length, hop_length=hop_length)[0]

    # Silence detection (frames below -60dB)
    silence_threshold = 10 ** (-60 / 20)  # -60dB in linear scale
    silent_frames = np.sum(rms_frames < silence_threshold)
    silence_ratio = silent_frames / len(rms_frames) if len(rms_frames) > 0 else 1.0

    # Simple SNR estimation
    # Use quietest 10% as noise estimate, loudest 50% as signal
    if len(rms_frames) > 10:
        sorted_rms = np.sort(rms_frames)
        noise_floor = np.mean(sorted_rms[:max(1, len(sorted_rms)//10)]) + 1e-10
        signal_level = np.mean(sorted_rms[len(sorted_rms)//2:]) + 1e-10
        snr_db = 20 * np.log10(signal_level / noise_floor)
    else:
        snr_db = 0.0

    # Clamp SNR to reasonable range
    snr_db = max(-10.0, min(60.0, snr_db))

    # Speech detection (simple energy-based VAD)
    # Frames with RMS > -45dB threshold likely contain speech
    speech_threshold = 10 ** (-45 / 20)  # -45dB in linear scale
    speech_frames = np.sum(rms_frames > speech_threshold)
    speech_ratio = speech_frames / len(rms_frames) if len(rms_frames) > 0 else 0.0
    speech_detected = speech_ratio > THRESHOLDS["speech_min"]

    return {
        "snr_db": float(snr_db),
        "rms_db": float(rms_db),
        "peak_db": float(peak_db),
        "clipping_ratio": float(clipping_ratio),
        "silence_ratio": float(silence_ratio),
        "speech_ratio": float(speech_ratio),
        "speech_detected": bool(speech_detected),
        "duration_seconds": float(duration)
    }


def _classify_quality(metrics: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Classify overall audio quality and identify specific issues.

    Returns:
        Tuple of (quality_level: str, issues: List[dict])
    """
    issues = []

    # SNR Check
    if metrics["snr_db"] < THRESHOLDS["snr_fair"]:
        issues.append({
            "type": "low_snr",
            "severity": "critical",
            "message": "High background noise detected"
        })
    elif metrics["snr_db"] < THRESHOLDS["snr_good"]:
        issues.append({
            "type": "low_snr",
            "severity": "warning",
            "message": "Moderate background noise"
        })

    # Volume Check
    if metrics["rms_db"] < THRESHOLDS["rms_very_quiet"]:
        issues.append({
            "type": "too_quiet",
            "severity": "critical",
            "message": "Audio volume is very low"
        })
    elif metrics["rms_db"] < THRESHOLDS["rms_too_quiet"]:
        issues.append({
            "type": "too_quiet",
            "severity": "warning",
            "message": "Audio volume is low"
        })

    # Clipping Check
    if metrics["clipping_ratio"] > THRESHOLDS["clipping_warn"]:
        issues.append({
            "type": "clipping",
            "severity": "warning",
            "message": "Audio distortion detected (clipping)"
        })

    # Silence Check
    if metrics["silence_ratio"] > THRESHOLDS["silence_high"]:
        issues.append({
            "type": "too_much_silence",
            "severity": "warning",
            "message": "Recording contains mostly silence"
        })

    # Speech Detection
    if not metrics["speech_detected"]:
        issues.append({
            "type": "no_speech",
            "severity": "critical",
            "message": "No speech detected in recording"
        })

    # Duration Check
    if metrics["duration_seconds"] < THRESHOLDS["duration_min"]:
        issues.append({
            "type": "too_short",
            "severity": "warning",
            "message": "Recording is very short"
        })
    elif metrics["duration_seconds"] > THRESHOLDS["duration_max"]:
        issues.append({
            "type": "too_long",
            "severity": "warning",
            "message": "Recording is unusually long"
        })

    # Classify overall quality
    critical_count = sum(1 for i in issues if i["severity"] == "critical")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")

    if critical_count > 0:
        overall_quality = "poor"
    elif warning_count > 1:
        overall_quality = "fair"
    elif warning_count == 1:
        overall_quality = "fair"
    else:
        overall_quality = "good"

    return overall_quality, issues


def _generate_summary(overall_quality: str, issues: List[Dict[str, Any]]) -> str:
    """Generate a human-readable summary message."""

    if overall_quality == "good":
        return "Audio quality is good for transcription."

    # Collect issue messages
    critical_messages = [i["message"] for i in issues if i["severity"] == "critical"]
    warning_messages = [i["message"] for i in issues if i["severity"] == "warning"]

    parts = []

    if overall_quality == "poor":
        parts.append("Audio quality is poor.")
    else:
        parts.append("Audio quality is fair.")

    # Add specific issues
    all_messages = critical_messages + warning_messages
    if all_messages:
        parts.append(" ".join(all_messages[:3]) + ".")  # Limit to 3 issues

    # Add recommendation based on quality
    if overall_quality == "poor":
        parts.append("Transcription accuracy may be significantly reduced. Consider re-recording in a quieter environment.")
    else:
        parts.append("Results should be acceptable but may contain some errors.")

    return " ".join(parts)


def _get_default_result(reason: str, duration_seconds: float = 0.0) -> Dict[str, Any]:
    """Return a default result when analysis cannot be performed.

    The metrics dict mirrors the schema returned by `_calculate_metrics` —
    every field consumers rely on is present with a sentinel value so
    downstream code paths (validation gates, dashboard rendering) are stable.
    """
    return {
        "overall_quality": "unknown",
        "is_acceptable": True,  # Don't block processing
        "issues": [{
            "type": "analysis_skipped",
            "severity": "warning",
            "message": reason
        }],
        "metrics": {
            "snr_db": 0.0,
            "rms_db": 0.0,
            "peak_db": 0.0,
            "clipping_ratio": 0.0,
            "silence_ratio": 0.0,
            "speech_ratio": 0.0,
            "speech_detected": False,
            "duration_seconds": float(duration_seconds),
        },
        "summary_message": f"Audio quality analysis skipped: {reason}"
    }
