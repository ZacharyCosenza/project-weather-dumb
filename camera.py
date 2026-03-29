"""
test_camera.py — pull one 511NY camera image and save as PNG

pip install requests pillow
API key: https://511ny.org/developers/resources
"""

import io, sys, subprocess, tempfile, requests
from pathlib import Path
from PIL import Image

API_KEY = "your_key_here"
OUT     = Path("test_camera.png")


def get_cameras(api_key: str) -> list[dict]:
    r = requests.get("https://511ny.org/api/getcameras",
                     params={"key": api_key, "format": "json"}, timeout=15)
    r.raise_for_status()
    return r.json()


def nyc_cameras(cameras: list[dict]) -> list[dict]:
    return [c for c in cameras
            if 40.4 <= c["Latitude"] <= 40.95
            and -74.3 <= c["Longitude"] <= -73.7
            and not c["Disabled"] and not c["Blocked"]
            and c.get("VideoUrl")]


def snapshot_from_stream(url: str) -> Image.Image:
    # Try direct JPEG snapshot first
    jpeg_url = url.replace("playlist.m3u8", "snapshot.jpg")
    try:
        r = requests.get(jpeg_url, timeout=10)
        if r.status_code == 200 and r.headers["content-type"].startswith("image"):
            return Image.open(io.BytesIO(r.content))
    except Exception:
        pass

    # Fall back to ffmpeg frame grab
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp = f.name
    subprocess.run(
        ["ffmpeg", "-i", url, "-frames:v", "1", "-q:v", "2", "-y", tmp],
        capture_output=True, timeout=20, check=True
    )
    return Image.open(tmp)


if __name__ == "__main__":
    print("Fetching camera list...")
    cameras = nyc_cameras(get_cameras(API_KEY))
    print(f"Found {len(cameras)} NYC cameras")

    if not cameras:
        sys.exit("No cameras found — check API key")

    cam = cameras[0]
    print(f"Trying: {cam['Name']} ({cam['Latitude']}, {cam['Longitude']})")
    print(f"Stream: {cam['VideoUrl']}")

    img = snapshot_from_stream(cam["VideoUrl"])
    img.save(OUT)
    print(f"Saved {OUT}  ({img.size[0]}x{img.size[1]})")