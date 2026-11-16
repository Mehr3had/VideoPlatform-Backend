import json
import shutil
import subprocess
import uuid

from pathlib import Path


class HLSGenerationError(Exception):
    """Raised when HLS generation fails."""


class UnsupportedHLSInputError(HLSGenerationError):
    """Raised when the source codecs are not supported."""


def probe_video(video_path: str | Path) -> dict:
    """
    Extract video and audio stream information using FFprobe.
    """

    ffprobe_path = shutil.which("ffprobe")

    if not ffprobe_path:
        raise HLSGenerationError("FFprobe was not found.")

    try:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v", "error",
                "-show_entries",
                "stream=codec_type,codec_name,width,height",
                "-of", "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return json.loads(result.stdout)

    except (
        subprocess.SubprocessError,
        json.JSONDecodeError,
        OSError,
    ) as error:
        raise HLSGenerationError(
            f"Could not inspect video: {error}"
        ) from error


def generate_hls(
    video_path: str | Path,
    output_dir: str | Path,
    segment_duration: int = 6,
) -> Path:
    """
    Generate HLS using stream copy.

    Supports H.264 video and AAC audio.
    Does not re-encode the source.
    """

    video_path = Path(video_path)
    output_dir = Path(output_dir)

    if not video_path.is_file():
        raise HLSGenerationError(
            f"Video file does not exist: {video_path}"
        )

    if segment_duration < 2:
        raise ValueError("Segment duration must be at least 2 seconds.")

    ffmpeg_path = shutil.which("ffmpeg")

    if not ffmpeg_path:
        raise HLSGenerationError("FFmpeg was not found.")

    # Inspect the source before processing.
    media_info = probe_video(video_path)

    streams = media_info.get("streams", [])

    video_stream = next(
        (
            stream
            for stream in streams
            if stream.get("codec_type") == "video"
        ),
        None,
    )

    audio_stream = next(
        (
            stream
            for stream in streams
            if stream.get("codec_type") == "audio"
        ),
        None,
    )

    if not video_stream:
        raise UnsupportedHLSInputError(
            "The input does not contain a video stream."
        )

    # Only use stream copy for codecs supported by our initial HLS pipeline.
    if video_stream.get("codec_name") != "h264":
        raise UnsupportedHLSInputError(
            "HLS stream copy currently requires H.264 video."
        )

    if (
        audio_stream
        and audio_stream.get("codec_name") != "aac"
    ):
        raise UnsupportedHLSInputError(
            "HLS stream copy currently requires AAC audio."
        )

    # Generate into a temporary directory first.
    temp_dir = output_dir.with_name(
        f"{output_dir.name}.tmp-{uuid.uuid4().hex}"
    )

    generation_id = uuid.uuid4().hex

    temp_dir.mkdir(parents=True, exist_ok=False)

    playlist_path = temp_dir / "index.m3u8"

    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(video_path),
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-c", "copy",
        "-f", "hls",
        "-hls_time", str(segment_duration),
        "-hls_playlist_type", "vod",
        "-hls_segment_filename",
        str(temp_dir / f"segment_{generation_id}_%03d.ts"),
        str(playlist_path),
    ]

    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            check=True,
        )

        if not playlist_path.is_file():
            raise HLSGenerationError(
                "FFmpeg did not generate the HLS playlist."
            )

        segments = list(temp_dir.glob("segment_*.ts"))

        if not segments:
            raise HLSGenerationError(
                "FFmpeg did not generate any HLS segments."
            )

        # Replace the previous output only after successful generation.
        backup_dir = output_dir.with_name(
            f"{output_dir.name}.old-{uuid.uuid4().hex}"
        )

        had_previous_output = output_dir.exists()

        try:
            if had_previous_output:
                output_dir.rename(backup_dir)

            temp_dir.rename(output_dir)

        except OSError as replace_error:
            if (
                had_previous_output
                and backup_dir.exists()
                and not output_dir.exists()
            ):
                try:
                    backup_dir.rename(output_dir)

                except OSError as restore_error:
                    raise HLSGenerationError(
                        "HLS replacement failed and the previous "
                        f"output could not be restored. "
                        f"Backup is preserved at: {backup_dir}. "
                        f"Restore error: {restore_error}"
                    ) from replace_error

            raise

        if backup_dir.exists():
            shutil.rmtree(
                backup_dir,
                ignore_errors=True,
            )

        return output_dir / "index.m3u8"

    except subprocess.CalledProcessError as error:
        details = (error.stderr or "").strip()

        raise HLSGenerationError(
            f"FFmpeg failed: {details[-1500:]}"
        ) from error

    except subprocess.TimeoutExpired as error:
        raise HLSGenerationError(
            "HLS generation timed out."
        ) from error

    except OSError as error:
        raise HLSGenerationError(
            f"HLS file operation failed: {error}"
        ) from error

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)