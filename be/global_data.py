import os

_cache_base = os.environ.get(
    "CACHE_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "nginx", "html")),
)
_log_base = os.environ.get(
    "LOG_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "nginx", "logs")),
)


class Config:
    nginx_access_log_path = os.path.join(_log_base, "file.access.log")
    nginx_video_path = os.path.join(_cache_base, "videos")
    nginx_comic_path = os.path.join(_cache_base, "comics")
    nginx_image_path = os.path.join(_cache_base, "images")
    # Last image scan result, loaded at startup (see api.images.load_snapshot).
    # Kept outside nginx_image_path so nginx never serves it.
    image_snapshot_path = os.path.join(_cache_base, "image-store.json")

    class Comic:
        scan_pathes = [os.environ.get("COMIC_SCAN_PATH", "/data/comics")]
        # Where image-album -> comic conversions are written. Unset means
        # "<first scan path>/converted", so the output is still picked up by scans.
        convert_path = os.environ.get("COMIC_CONVERT_PATH")

    class Video:
        scan_pathes = [os.environ.get("VIDEO_SCAN_PATH", "/data/videos")]

    class Image:
        liked_path = "/data/liked"
        scan_pathes = [os.environ.get("IMAGE_SCAN_PATH", "/data/images"), liked_path]

if not os.path.exists(Config.nginx_video_path):
    os.makedirs(Config.nginx_video_path)
if not os.path.exists(Config.nginx_comic_path):
    os.makedirs(Config.nginx_comic_path)
if not os.path.exists(Config.nginx_image_path):
    os.makedirs(Config.nginx_image_path)

# Ensure liked folder exists and is symlinked into nginx at startup
try:
    os.makedirs(Config.Image.liked_path, exist_ok=True)
    _liked_link = os.path.join(Config.nginx_image_path, "liked")
    if not os.path.exists(_liked_link):
        os.symlink(Config.Image.liked_path, _liked_link)
except OSError:
    pass