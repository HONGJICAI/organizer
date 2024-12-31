import hashlib
import os


def str2md5(s: str):
    m = hashlib.md5()
    m.update(s.encode("utf-8"))
    return m.hexdigest()


def create_soft_link(src: str, dst: str):
    if not os.path.exists(dst):
        os.symlink(src, dst)
