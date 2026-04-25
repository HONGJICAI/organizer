import os


err_message = []


class Config:
    nginx_access_log_path = "/config/logs/file.access.log"
    nginx_video_path = "/config/cache/videos"
    nginx_comic_path = "/config/cache/comics"
    nginx_image_path = "/config/cache/images"

    class Comic:
        scan_pathes = [os.environ.get("COMIC_SCAN_PATH", "/data/comics")]

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