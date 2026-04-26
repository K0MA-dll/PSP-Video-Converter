![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)
![FFmpeg](https://img.shields.io/badge/FFmpeg-enabled-green?logo=ffmpeg)
![Status](https://img.shields.io/badge/status-stable-brightgreen)
![Platform](https://img.shields.io/badge/platform-windows-lightgrey)

# 🎬 PSP Video Converter

A lightweight video converter built with **Python + PySide6 + FFmpeg**, optimized for **PlayStation Portable (PSP)**.
This software isn’t meant to be the most feature-rich, but it focuses on simplicity and reliability. It converts videos to PSP format without requiring any complex settings, 
everything is designed to be straightforward and easy to use.

## 📸 Preview


<img width="958" height="539" alt="Screen2" src="https://github.com/user-attachments/assets/4731d4ff-843e-4e8b-894e-323fda7139d4" />

## 📦 Download

<p align="center">
  <a href="https://github.com/K0MA-dll/PSP-Video-Converter/releases/latest">
    <img src="https://img.shields.io/badge/⬇%20DOWNLOAD-EXE-blue?style=for-the-badge&logo=github">
  </a>
</p>

## ✨ Features
- Convert any video to PSP format (480x272)
- Drag & drop support
- FFmpeg-powered fast conversion
- Real-time progress tracking
- Pause / Resume / Stop conversion
- Quality presets (High / Medium / Low size)
- Custom output folder
- Multi-threaded processing

## 🖥️ Requirements
- Python 3.9+
- PySide6
- FFmpeg (included or placed in ffmpeg/ folder)

Install dependencies:
pip install PySide6

## 📦 Usage
Clone the repository:
```bash
git clone https://github.com/K0MA-dll/PSP-Video-Converter.git
```
```bash
cd PSP-Video-Converter
```

Run the application:
python psp_video_converter.py

## ⚙️ How it works

This application is built using:

### 🎥 FFmpeg backend
- Handles video conversion
- Converts videos into PSP-compatible format (480x272)
- Encodes using H.264 + AAC

### 🖥️ PySide6 UI
- Provides graphical interface
- Handles drag & drop
- Displays progress and controls

### 🧵 Threading system
- Conversion runs in background thread
- Prevents UI freezing
- Allows pause / resume / stop

## 🎮 Output format
- Resolution: 480x272
- Codec: H.264 (baseline profile)
- Audio: AAC
- Format: MP4 (PSP compatible)

## 📁 Output folder
Default location:
~/Videos/PSP

You can change it inside the app.

## ⚠️ Notes
- FFmpeg must be installed or placed in the ffmpeg/ folder
- Large files may take time depending on quality preset

## 📜 License
MIT License

## 🙌 Author
Made with ❤️ by K0MA.dll
