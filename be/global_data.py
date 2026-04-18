import os


err_message = []


class Config:
    nginx_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "nginx"))
    nginx_access_log_path = os.path.join(nginx_path, "logs", "file.access.log")
    nginx_html_path = os.path.join(nginx_path, "html")
    nginx_video_path = os.path.join(nginx_html_path, "videos")
    nginx_comic_path = os.path.join(nginx_html_path, "comics")
    nginx_image_path = os.path.join(nginx_html_path, "images")

    class Comic:
        scan_pathes = [os.environ.get("COMIC_SCAN_PATH", "/data/comics")]

    class Video:
        scan_pathes = [os.environ.get("VIDEO_SCAN_PATH", "/data/videos")]

if not os.path.exists(Config.nginx_video_path):
    os.makedirs(Config.nginx_video_path)
if not os.path.exists(Config.nginx_comic_path):
    os.makedirs(Config.nginx_comic_path)
if not os.path.exists(Config.nginx_image_path):
    os.makedirs(Config.nginx_image_path)