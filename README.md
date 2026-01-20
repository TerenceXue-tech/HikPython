# HikPython

## 0. Introduction

This repository implements a complete pipeline for **Hikrobot industrial camera image acquisition → cloud upload → real-time image update on a client web page**.  
The system runs on a Raspberry Pi platform and is developed in Python, supporting camera parameter debugging, scheduled image capture, cloud synchronization, and real-time web visualization.

---

## 1. Preparation

### 1.1 Hardware

- Hikrobot USB3.0 area-scan camera: MV-CU060-10UC  
- Raspberry Pi 5 (8GB RAM)

### 1.2 Operating System

- Ubuntu 24.04 (ARM64)

### 1.3 Main Python Dependencies

- Hikrobot Camera SDK  
- Huawei Cloud OBS Python SDK  
- Flask (for client-side real-time web display)  
- PyQt5 (for camera parameter debugging only)

### 1.4 Huawei Cloud OBS Setup

1. Create an OBS bucket  
2. Obtain your Huawei Cloud Access Key (AK) and Secret Key (SK)  
Reference documentation:  
https://support.huaweicloud.com/obs/index.html

### 1.5 Quick Installation

```bash
conda env create -f environment.yml
conda activate hik
```

---

## 2. Camera Test

Use the following script to verify that the Hikrobot camera can be correctly detected and opened:

```bash
python ./myscripts/test_camera.py
```

---

## 3. Camera Parameter Debugging

Use the official demo program to configure exposure, gain, resolution, and other camera parameters:

```bash
python ./AreaScanCamera/BasicDemo/BasicDemo.py
```

---

## 4. Main Functions

### 4.1 Start Cloud Upload Service

Start the background program that uploads captured images to Huawei Cloud OBS:

```bash
python ./myscripts/upload_cloud.py
```

### 4.2 Start Image Acquisition

Control the camera to capture images periodically and save them locally:

```bash
python ./myscripts/get_image.py
```

### 4.3 Client-Side Real-Time Display

Download the latest images from the cloud and display them on a web page with real-time updates:

```bash
python ./myscripts/download_display.py
```

---

## 5. Directory Structure

```text
HikPython/
├── AreaScanCamera/          # Hikrobot official demos and parameter tools
├── myscripts/               # Custom scripts
│   ├── test_camera.py
│   ├── get_image.py
│   ├── upload_cloud.py
│   └── download_display.py
├── environment.yml          # Conda environment configuration
└── README.md
```

---

## 6. Notes

- This project is designed for ARM64 architecture (Raspberry Pi)
- PyQt5 is only required for debugging and is not necessary for deployment
- Remote operation via SSH is recommended for headless setups
