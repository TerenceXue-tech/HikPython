import os
import time
import threading
import traceback

from flask import Flask, Response, send_file, render_template_string, jsonify

from obs import ObsClient
from obs import GetObjectHeader


# =======================
# 配置区
# =======================
ak = "HPUA2W0ZB0ABZVTTUEVK"
sk = "h1FmUfOJdjuWGKy3vFXH89l4IkyjdZSj99Q3aseC"
server = "https://obs.cn-north-4.myhuaweicloud.com"

bucketName = "lurgigpt"
prefix = "captures/"   # 云上“目录前缀”

poll_interval_sec = 5.0   
local_dir = "/home/xtc/Documents/HikPython/downloads" 



# 仅识别这些图片后缀（按需增删）
# 仅识别这些图片后缀（按需增删）
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def is_image_key(key: str) -> bool:
    ext = os.path.splitext(key)[1].lower()
    return ext in IMAGE_EXTS


def safe_basename_from_key(key: str) -> str:
    return os.path.basename(key)


def find_latest_key_by_lexicographic(obsClient: ObsClient):
    marker = None
    latest_key = None

    while True:
        resp = obsClient.listObjects(bucketName, prefix=prefix, marker=marker, max_keys=1000)
        if resp.status >= 300:
            raise RuntimeError(f"listObjects failed: {resp.errorCode} {resp.errorMessage}")

        contents = getattr(resp.body, "contents", None) or []
        for obj in contents:
            key = getattr(obj, "key", None)
            if not key or not is_image_key(key):
                continue
            if latest_key is None or key > latest_key:
                latest_key = key

        is_truncated = getattr(resp.body, "is_truncated", False)
        next_marker = getattr(resp.body, "next_marker", None)
        if not is_truncated or not next_marker:
            break
        marker = next_marker

    return latest_key


def download_keep_name(obsClient: ObsClient, objectKey: str) -> str:
    ensure_dir(local_dir)

    filename = safe_basename_from_key(objectKey)
    local_path = os.path.join(local_dir, filename)

    # 已存在则不重复下载
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return local_path

    headers = GetObjectHeader()
    tmp_path = local_path + ".tmp"

    resp = obsClient.getObject(bucketName, objectKey, tmp_path, headers=headers)
    if resp.status < 300:
        os.replace(tmp_path, local_path)
        return local_path
    else:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise RuntimeError(f"getObject failed: {resp.errorCode} {resp.errorMessage}")


class Fetcher(threading.Thread):
    daemon = True

    def __init__(self, obsClient: ObsClient):
        super().__init__()
        self.obsClient = obsClient
        self.latest_key = None
        self.latest_local_path = None
        self.last_err = None

    def run(self):
        while True:
            try:
                latest_key = find_latest_key_by_lexicographic(self.obsClient)

                if not latest_key:
                    self.last_err = "OBS 上当前没有图片对象（或不匹配后缀过滤）"
                    time.sleep(poll_interval_sec)
                    continue

                if latest_key != self.latest_key:
                    local_path = download_keep_name(self.obsClient, latest_key)
                    self.latest_key = latest_key
                    self.latest_local_path = local_path
                    self.last_err = None
                    print(f"[OK] New latest: {latest_key} -> {local_path}")

                time.sleep(poll_interval_sec)

            except Exception as e:
                self.last_err = str(e)
                print("[ERROR] Fetch loop error, will retry.")
                print(traceback.format_exc())
                time.sleep(2.0)


HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Latest OBS Image</title>
  <style>
    body { font-family: sans-serif; margin: 20px; }
    .meta { margin-bottom: 12px; color: #444; }
    img { max-width: 100%; height: auto; border: 1px solid #ddd; }
    .err { color: #b00020; }
    code { background: #f6f6f6; padding: 2px 4px; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="meta">
    <div><b>Bucket:</b> <span id="bucket">{{ bucket }}</span> &nbsp; <b>Prefix:</b> <span id="prefix">{{ prefix }}</span></div>
    <div><b>Latest Key:</b> <code id="latest_key">-</code></div>
    <div><b>Latest Local:</b> <code id="latest_local">-</code></div>
    <div id="status_line"><b>Status:</b> <span id="last_err">OK</span></div>
  </div>

  <!-- 注意：图片URL不再固定 /latest，而是切换到 /image/<filename>，避免浏览器“看起来不更新” -->
  <img id="img" src="" alt="latest">

<script>
  let currentKey = null;

  function setStatus(text, isErr) {
    const line = document.getElementById("status_line");
    const span = document.getElementById("last_err");
    span.textContent = text || "OK";
    if (isErr) line.classList.add("err");
    else line.classList.remove("err");
  }

  async function refreshStatusAndMaybeImage() {
    try {
      const r = await fetch("/status?ts=" + Date.now(), { cache: "no-store" });
      if (!r.ok) return;
      const data = await r.json();

      document.getElementById("latest_key").textContent = data.latest_key || "-";
      document.getElementById("latest_local").textContent = data.latest_local || "-";
      setStatus(data.last_err || "OK", !!data.last_err);

      // 只有当：拿到新key + 本地文件已准备好，才切换图片
      if (data.latest_key && data.latest_ready && data.latest_key !== currentKey) {
        currentKey = data.latest_key;

        // 取文件名（去掉前缀路径）
        const filename = (data.latest_key.split("/").pop());
        const img = document.getElementById("img");

        // 关键：URL 包含 filename + ts，保证每次新图都是新资源
        img.src = "/image/" + encodeURIComponent(filename) + "?ts=" + Date.now();
      }
    } catch (e) {
      // 忽略偶发网络错误
    }
  }

  // 每 5 秒刷新状态；图片只在 key 变化时切换
  setInterval(refreshStatusAndMaybeImage, 5000);
  refreshStatusAndMaybeImage();
</script>
</body>
</html>
"""

app = Flask(__name__)
fetcher = None


@app.route("/")
def index():
    return render_template_string(
        HTML,
        bucket=bucketName,
        prefix=prefix,
    )


@app.route("/status")
def status():
    latest_key = getattr(fetcher, "latest_key", None) if fetcher else None
    latest_local = getattr(fetcher, "latest_local_path", None) if fetcher else None
    last_err = getattr(fetcher, "last_err", None) if fetcher else "Fetcher not started"

    latest_ready = bool(latest_local) and os.path.exists(latest_local) and os.path.getsize(latest_local) > 0

    return jsonify({
        "latest_key": latest_key,
        "latest_local": latest_local,
        "latest_ready": latest_ready,
        "last_err": last_err,
    })


@app.route("/image/<path:filename>")
def image_file(filename: str):
    """
    按文件名返回本地图片。
    这样前端每次切换到新 filename，浏览器一定重新拉取并渲染新图。
    """
    # 安全：只允许 basename，避免路径穿越
    safe_name = os.path.basename(filename)
    local_path = os.path.join(local_dir, safe_name)

    if not os.path.exists(local_path) or os.path.getsize(local_path) <= 0:
        return Response("image not ready", status=404)

    resp = send_file(local_path, conditional=False)  # 关闭条件请求，减少 304 影响
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def main():
    global fetcher

    if not ak or not sk:
        raise RuntimeError("未检测到环境变量 AccessKeyID / SecretAccessKey，请先设置后再运行。")

    ensure_dir(local_dir)

    obsClient = ObsClient(access_key_id=ak, secret_access_key=sk, server=server)

    fetcher = Fetcher(obsClient)
    fetcher.start()

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()