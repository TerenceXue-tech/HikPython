import os
import time
import traceback
from obs import ObsClient, PutObjectHeader


AK = "your AK"
SK = "your SK"
SERVER = "https://obs.cn-north-4.myhuaweicloud.com"

if not AK or not SK:
    raise RuntimeError("未检测到环境变量 AccessKeyID / SecretAccessKey，请先设置后再运行。")

# ========= 监控配置 =========
WATCH_DIR = "/home/xtc/Documents/HikPython/captures"   # 你要监控的本地目录
BUCKET_NAME = "your name"
REMOTE_PREFIX = "captures/"  # 云端对象名前缀，可为空 ""；例如 captures/xxx.png
POLL_INTERVAL_SEC = 5.0      # 轮询间隔：目录空时每隔多久看一次
STABLE_WAIT_SEC = 0.3        # 文件稳定等待：避免刚写完就上传（简单稳妥）

# 只处理这些图片后缀（可按需增删）
IMAGE_EXTS = {".png", ".jpg"}


def is_image_file(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTS


def pick_one_image(path: str) -> str | None:
    """
    从目录中挑一张图片（按修改时间最早的优先）。
    返回完整路径；若没有则返回 None。
    """
    try:
        files = []
        for name in os.listdir(path):
            full = os.path.join(path, name)
            if os.path.isfile(full) and is_image_file(name):
                files.append(full)

        if not files:
            return None

        files.sort(key=lambda p: os.path.getmtime(p))
        return files[0]
    except FileNotFoundError:
        os.makedirs(path, exist_ok=True)
        return None


def wait_file_stable(file_path: str, stable_wait: float = STABLE_WAIT_SEC) -> None:
    """
    简单检查文件大小在短时间内不再变化，降低“写入中被上传”的概率。
    """
    s1 = os.path.getsize(file_path)
    time.sleep(stable_wait)
    s2 = os.path.getsize(file_path)
    if s2 != s1:
        # 再等一次
        time.sleep(stable_wait)


def guess_content_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".png":
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".bmp":
        return "image/bmp"
    if ext in {".tif", ".tiff"}:
        return "image/tiff"
    if ext == ".webp":
        return "image/webp"
    return "application/octet-stream"


def upload_then_delete(obs_client: ObsClient, local_path: str) -> None:
    """
    上传成功 -> 删除本地文件；失败 -> 保留本地文件，等待下次重试。
    """
    filename = os.path.basename(local_path)
    object_key = f"{REMOTE_PREFIX}{filename}" if REMOTE_PREFIX else filename

    headers = PutObjectHeader()
    headers.contentType = guess_content_type(local_path)

    wait_file_stable(local_path)

    resp = obs_client.putFile(BUCKET_NAME, object_key, local_path, headers)

    if resp.status < 300:
        print(f"[OK] Uploaded: {local_path} -> obs://{BUCKET_NAME}/{object_key}  etag={resp.body.etag}")
        try:
            os.remove(local_path)
            print(f"[OK] Deleted local file: {local_path}")
        except Exception as e:
            print(f"[WARN] Upload succeeded but failed to delete local file: {local_path}, err={e}")
    else:
        print(f"[FAIL] Upload failed: {local_path}")
        print("requestId:", resp.requestId)
        print("errorCode:", resp.errorCode)
        print("errorMessage:", resp.errorMessage)


def main():
    obs_client = ObsClient(access_key_id=AK, secret_access_key=SK, server=SERVER)

    print(f"Watching folder: {WATCH_DIR}")
    print(f"Bucket: {BUCKET_NAME}, prefix: {REMOTE_PREFIX!r}")
    print("Loop started. (Ctrl+C to stop)")

    while True:
        try:
            img_path = pick_one_image(WATCH_DIR)
            if img_path is None:
                time.sleep(POLL_INTERVAL_SEC)
                continue

            upload_then_delete(obs_client, img_path)

        except KeyboardInterrupt:
            print("\nStopped by user.")
            break
        except Exception:
            print("[EXCEPTION] Loop error, will continue.")
            print(traceback.format_exc())
            time.sleep(1.0)


if __name__ == "__main__":
    main()
