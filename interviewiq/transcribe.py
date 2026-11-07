"""Audio transcription via Groq Whisper API."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Allowed audio formats and max file size
ALLOWED_EXTENSIONS = {'.webm', '.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.ogg'}
MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB (Groq's limit)


class TranscriptionError(Exception):
    """Transcription failed or was rejected."""


def transcribe_audio(audio_file, api_key: str | None = None, model: str = "whisper-large-v3-turbo") -> str:
    """
    Transcribe audio file using Groq Whisper API.
    
    Args:
        audio_file: File-like object or path to audio file
        api_key: Groq API key (required)
        model: Whisper model to use
        
    Returns:
        Transcribed text
        
    Raises:
        TranscriptionError: If transcription fails
    """
    if not api_key:
        raise TranscriptionError("GROQ_API_KEY not configured")
    
    try:
        import groq
    except ImportError:
        raise TranscriptionError("groq package not installed")
    
    client = groq.Groq(api_key=api_key, timeout=30.0, max_retries=1)
    
    try:
        # Groq expects a file-like object with a .name attribute
        response = client.audio.transcriptions.create(
            file=audio_file,
            model=model,
            response_format="text",  # Plain text is simpler than JSON
            temperature=0.0,  # Deterministic output
        )
        
        # Response is the text directly when format is "text"
        text = response if isinstance(response, str) else getattr(response, 'text', '')
        
        if not text or not text.strip():
            raise TranscriptionError("Transcription returned empty text")
        
        return text.strip()
        
    except Exception as exc:
        # Log the actual error but return a user-friendly message
        log.warning(f"Whisper transcription failed: {exc}")
        
        if "api key" in str(exc).lower():
            raise TranscriptionError("Invalid API key")
        elif "rate limit" in str(exc).lower():
            raise TranscriptionError("Rate limit exceeded, please try again in a moment")
        elif "timeout" in str(exc).lower():
            raise TranscriptionError("Transcription timed out")
        elif "file" in str(exc).lower() or "format" in str(exc).lower():
            raise TranscriptionError("Unsupported audio format")
        else:
            raise TranscriptionError(f"Transcription failed: {str(exc)[:100]}")


def validate_audio_file(filename: str, size: int) -> None:
    """
    Validate uploaded audio file.
    
    Args:
        filename: Original filename
        size: File size in bytes
        
    Raises:
        TranscriptionError: If file is invalid
    """
    if not filename:
        raise TranscriptionError("No file provided")
    
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise TranscriptionError(f"Unsupported audio format: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
    
    if size > MAX_AUDIO_SIZE:
        raise TranscriptionError(f"Audio file too large: {size / 1024 / 1024:.1f}MB (max: 25MB)")
    
    if size == 0:
        raise TranscriptionError("Audio file is empty")


def save_temp_audio(file_storage) -> tuple[str, str]:
    """
    Save uploaded file to a temporary location.
    
    Args:
        file_storage: Werkzeug FileStorage object
        
    Returns:
        Tuple of (temp_path, original_filename)
        
    Raises:
        TranscriptionError: If save fails
    """
    try:
        # Get file extension from original filename
        ext = Path(file_storage.filename).suffix.lower()
        
        # Create temporary file with the correct extension
        # delete=False so we can close it and let Groq open it
        fd, temp_path = tempfile.mkstemp(suffix=ext, prefix='interviewiq_audio_')
        
        try:
            # Close the file descriptor and save via FileStorage
            os.close(fd)
            file_storage.save(temp_path)
            return temp_path, file_storage.filename
        except Exception:
            # Clean up on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
            
    except Exception as exc:
        log.error(f"Failed to save uploaded audio: {exc}")
        raise TranscriptionError("Failed to save audio file")


def cleanup_temp_file(path: str) -> None:
    """Safely delete a temporary file."""
    if path:
        try:
            os.unlink(path)
        except OSError as exc:
            log.warning(f"Failed to delete temp file {path}: {exc}")
