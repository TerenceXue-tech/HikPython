import os
import sys
import time
import cv2
import numpy as np
from datetime import datetime
from ctypes import POINTER, c_ubyte, cast, byref, memmove, memset, sizeof

sys.path.append("/home/xtc/Documents/HikPython/MvImport")
from MvCameraControl_class import *

# ===== 固定配置（按你要求：不需要用户输入）=====
DEVICE_INDEX = 0
INTERVAL_SEC = 20
SAVE_DIR = "./captures"
GET_TIMEOUT_MS = 1000          # GetImageBuffer 超时
FAIL_SLEEP_SEC = 0.05          # 取不到帧时短暂休眠，避免空转占CPU


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def enum_devices():
    tlayerType = MV_GIGE_DEVICE | MV_USB_DEVICE | MV_UNKNOW_DEVICE | MV_1394_DEVICE | MV_CAMERALINK_DEVICE
    deviceList = MV_CC_DEVICE_INFO_LIST()
    ret = MvCamera.MV_CC_EnumDevices(tlayerType, deviceList)
    if ret != 0:
        raise RuntimeError(f"MV_CC_EnumDevices failed ret=0x{ret:x}")
    if deviceList.nDeviceNum == 0:
        raise RuntimeError("No camera devices found")
    return deviceList


def create_and_open_camera(deviceList, index: int):
    cam = MvCamera()
    stDeviceList = cast(deviceList.pDeviceInfo[index], POINTER(MV_CC_DEVICE_INFO)).contents

    ret = cam.MV_CC_CreateHandleWithoutLog(stDeviceList)
    if ret != 0:
        raise RuntimeError(f"MV_CC_CreateHandleWithoutLog failed ret=0x{ret:x}")

    ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
    if ret != 0:
        raise RuntimeError(f"MV_CC_OpenDevice failed ret=0x{ret:x}")

    return cam


def start_grabbing(cam):
    ret = cam.MV_CC_StartGrabbing()
    if ret != 0:
        raise RuntimeError(f"MV_CC_StartGrabbing failed ret=0x{ret:x}")


def stop_close_destroy(cam):
    # 尽量把资源释放干净
    try:
        cam.MV_CC_StopGrabbing()
    except Exception:
        pass
    try:
        cam.MV_CC_CloseDevice()
    except Exception:
        pass
    try:
        cam.MV_CC_DestroyHandle()
    except Exception:
        pass


def save_png_from_raw(raw: np.ndarray, info, out_path: str) -> bool:
    w, h = int(info.nWidth), int(info.nHeight)
    pixel_type = int(info.enPixelType)

    # Mono8 -> 灰度PNG
    if pixel_type == 17301505:
        gray = raw.reshape((h, w))
        return bool(cv2.imwrite(out_path, gray))

    # Bayer 8-bit 四种排列（把常见的都覆盖）
    bayer_map = {
        17301512: cv2.COLOR_BAYER_GR2BGR,  # BayerGR8（常见）
        17301513: cv2.COLOR_BAYER_RG2BGR,  # BayerRG8（你现在遇到的很可能就是这个）
        17301514: cv2.COLOR_BAYER_GB2BGR,  # BayerGB8
        17301515: cv2.COLOR_BAYER_BG2BGR,  # BayerBG8
    }
    if pixel_type in bayer_map:
        mono = raw.reshape((h, w))
        bgr = cv2.cvtColor(mono, bayer_map[pixel_type])
        return bool(cv2.imwrite(out_path, bgr))

    # RGB8 -> BGR -> 彩色PNG
    if pixel_type == 35127316:
        rgb = raw.reshape((h, w, 3))
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return bool(cv2.imwrite(out_path, bgr))

    # YUV422 -> BGR -> 彩色PNG
    if pixel_type == 34603039:
        yuv = raw.reshape((h, w, 2))
        bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_Y422)
        return bool(cv2.imwrite(out_path, bgr))

    return False

def set_exposure_time(cam, exposure_time: float):
    # 关闭自动曝光（建议做，否则 ExposureTime 可能被自动曝光覆盖）
    ret = cam.MV_CC_SetEnumValue("ExposureAuto", 0)
    # 有些机型/权限下这个节点可能不存在或不可写；不致命，但建议打印出来
    if ret != 0:
        print(f"[WARN] Set ExposureAuto=Off failed ret=0x{ret:x}")

    time.sleep(0.2)  # 你原 Demo 里也 sleep 了，保留更稳

    # 设置曝光时间（通常单位是 us）
    ret = cam.MV_CC_SetFloatValue("ExposureTime", float(exposure_time))
    if ret != 0:
        raise RuntimeError(f"Set ExposureTime={exposure_time} failed ret=0x{ret:x}")

    print(f"[OK] ExposureTime set to {exposure_time}")


def main():
    ensure_dir(SAVE_DIR)

    deviceList = enum_devices()
    if DEVICE_INDEX >= deviceList.nDeviceNum:
        raise RuntimeError(f"DEVICE_INDEX={DEVICE_INDEX} out of range (found {deviceList.nDeviceNum} devices)")

    cam = None
    stOutFrame = MV_FRAME_OUT()
    memset(byref(stOutFrame), 0, sizeof(stOutFrame))

    try:
        cam = create_and_open_camera(deviceList, DEVICE_INDEX)
        set_exposure_time(cam, 50000) #设置曝光时间
        start_grabbing(cam)

        next_ts = time.monotonic()  # 立即保存第一张
        while True:
            now = time.monotonic()
            if now < next_ts:
                time.sleep(min(0.2, next_ts - now))
                continue

            ret = cam.MV_CC_GetImageBuffer(stOutFrame, GET_TIMEOUT_MS)
            if ret != 0 or stOutFrame.pBufAddr is None:
                time.sleep(FAIL_SLEEP_SEC)
                continue

            info = stOutFrame.stFrameInfo
            frame_len = int(getattr(info, "nFrameLen", 0))

            # 兜底：老版本无 nFrameLen 时按常见像素类型估算
            if frame_len <= 0:
                w, h = int(info.nWidth), int(info.nHeight)
                pt = int(info.enPixelType)
                if pt in (17301505, 17301514):
                    frame_len = w * h
                elif pt == 35127316:
                    frame_len = w * h * 3
                elif pt == 34603039:
                    frame_len = w * h * 2
                else:
                    cam.MV_CC_FreeImageBuffer(stOutFrame)
                    time.sleep(FAIL_SLEEP_SEC)
                    continue

            buf = (c_ubyte * frame_len)()
            memmove(byref(buf), stOutFrame.pBufAddr, frame_len)
            raw = np.frombuffer(buf, dtype=np.uint8, count=frame_len)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            out_png = os.path.join(SAVE_DIR, f"img_{ts}.png")

            ok = save_png_from_raw(raw, info, out_png)
            if not ok:
                # 不支持的像素类型：保存原始 bin，便于你后续补转换
                out_bin = os.path.join(SAVE_DIR, f"img_{ts}_PixelType{int(info.enPixelType)}.bin")
                with open(out_bin, "wb") as f:
                    f.write(raw.tobytes())

            cam.MV_CC_FreeImageBuffer(stOutFrame)

            # 严格按节拍：每 5 秒一次
            next_ts += INTERVAL_SEC

    finally:
        if cam is not None:
            stop_close_destroy(cam)


if __name__ == "__main__":
    main()
