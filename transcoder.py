import subprocess
import os

def transcode(input_path, output_path):
    input_ext = os.path.splitext(input_path)[1].lower()
    output_ext = os.path.splitext(output_path)[1].lower()

    if input_ext == output_ext:
        # No transcoding needed
        os.rename(input_path, output_path)
        return True

    # Example: FLAC to ALAC
    if input_ext == ".flac" and output_ext == ".m4a":
        cmd = ["ffmpeg", "-y", "-i", input_path, "-c:a", "alac", output_path]
    # Example: FLAC to MP3
    elif input_ext == ".flac" and output_ext == ".mp3":
        cmd = ["ffmpeg", "-y", "-i", input_path, "-c:a", "libmp3lame", "-b:a", "320k", output_path]
    # Add more as needed
    else:
        return False

    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0