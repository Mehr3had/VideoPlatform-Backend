import json
import subprocess
import tempfile
from pathlib import Path

from django.core.files import File

from videos.models import VideoQuality


def get_video_resolution(video_path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "v:0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)
    stream = data["streams"][0]

    return stream["width"], stream["height"]


def generate_video_qualities(video):
    source_path = video.video_file.path

    _, height = get_video_resolution(source_path)

    resolutions = [480, 720, 1080]

    generated = []

    with tempfile.TemporaryDirectory() as temp_dir:

        for resolution in resolutions:

            if height < resolution:
                continue

            output_path = Path(temp_dir) / f"{resolution}p.mp4"

            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i", source_path,
                        "-map", "0:v:0",
                        "-map", "0:a?",
                        "-vf", f"scale=-2:{resolution}",
                        "-c:v", "libx264",
                        "-preset", "veryfast",
                        "-crf", "23",
                        "-c:a", "aac",
                        "-b:a", "128k",
                        "-movflags", "+faststart",
                        str(output_path),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                quality = VideoQuality(
                    video=video,
                    resolution=resolution,
                )

                with open(output_path, "rb") as file:
                    quality.video_file.save(
                        f"video_{video.id}_{resolution}p.mp4",
                        File(file),
                        save=True,
                    )
                generated.append(quality)

            except subprocess.CalledProcessError as error:
                print(
                    f"Failed to generate {resolution}p for video {video.id}: "
                    f"{error.stderr}"
                )

    return generated