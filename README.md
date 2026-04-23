# 🎬 PSP Video Converter

A lightweight video converter built with **Python + PySide6 + FFmpeg**, optimized for **PlayStation Portable (PSP)**.

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
git clone https://github.com/K0MA-dll/PSP-Video-Converter.git
cd PSP-Video-Converter

Run the application:
python psp_video_converter.py

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
