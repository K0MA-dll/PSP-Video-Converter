import sys
import subprocess
import tempfile
import uuid
import time
import re
import os
import platform
import logging
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem,
    QFileDialog, QProgressBar,
    QRadioButton, QButtonGroup, QMessageBox
)
from PySide6.QtCore import Qt, QObject, Signal, QThread, QMimeData, QTimer
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QIcon

# Logging
logging.basicConfig(
    filename='psp_converter.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Cross-platform FFmpeg paths
def resource_path(relative_path):
    """Returns correct path (dev or exe PyInstaller)"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


system = platform.system().lower()
if system == "windows":
    FFMPEG_PATH = resource_path("ffmpeg/ffmpeg.exe")
    FFPROBE_PATH = resource_path("ffmpeg/ffprobe.exe")
else:
    FFMPEG_PATH = resource_path("ffmpeg/ffmpeg")
    FFPROBE_PATH = resource_path("ffmpeg/ffprobe")

VIDEO_EXTS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg'}

# =========================================================
# PRESETS
# =========================================================
PRESETS = {
    "High quality": {"crf": 21, "a": 128},
    "Medium": {"crf": 23, "a": 112},
    "Low size": {"crf": 25, "a": 96},
}

# =========================================================
# SIGNALS THREAD SAFE
# =========================================================
class Signals(QObject):
    progress = Signal(str, float)
    status = Signal(str)
    finished = Signal()
    pause_toggle = Signal()

# =========================================================
# BACKEND FFmpeg
# =========================================================
class Converter(QThread):
    def __init__(self, files, signals, output_dir, aspect, preset):
        super().__init__()
        self.files = files
        self.signals = signals
        self.output_dir = Path(output_dir)
        self.aspect = aspect
        self.preset = preset
        self.stop_flag = False
        self.paused = False
        self.mutex = threading.Lock()
        self.total_durations = {}
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def parse_time(self, time_str):
        """converts HH:MM:SS.ss to secondes"""
        h, m, s = time_str.split(':')
        return int(h)*3600 + int(m)*60 + float(s)

    def get_duration(self, file):
        try:
            result = subprocess.run([
                FFPROBE_PATH,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file
            ], capture_output=True, text=True, timeout=10)

            duration = float(result.stdout.strip())
            self.total_durations[file] = duration
            return duration

        except Exception as e:
            logging.error(f"Duration error {file}: {e}")
            return 0

    def make_thumbnail(self, file):
        """generates thumbnail (async-safe)"""
        temp = None
        try:
            temp = Path(tempfile.gettempdir()) / f"psp_{uuid.uuid4().hex}.jpg"
            subprocess.run([
                FFMPEG_PATH, "-y", "-i", file,
                "-ss", "00:00:02", "-vframes", "1",
                "-vf", "scale=120:70:force_original_aspect_ratio=decrease",
                str(temp)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, 
            timeout=30, check=False)
            
            if temp.exists():
                pix = QPixmap(str(temp))
                if not pix.isNull():
                    return pix
        except Exception as e:
            logging.error(f"Thumbnail error {file}: {e}")
        finally:
            if temp and temp.exists():
                try:
                    temp.unlink()
                except:
                    pass
        return None

    def build_cmd(self, inp, outp):
        """builds command FFmpeg optimised PSP"""
        if self.aspect == "keep":
            vf = (
                "scale=480:272:force_original_aspect_ratio=decrease,"
                "pad=480:272:(ow-iw)/2:(oh-ih)/2:black"
            )
        else:
            vf = "scale=480:272,setsar=1"

        return [
            FFMPEG_PATH, "-y",
            "-i", inp,
            "-vf", vf,
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            "-profile:v", "baseline",
            "-level", "3.0",  
            "-preset", "medium",
            "-crf", str(self.preset["crf"]),
            "-threads", "0",  
            "-c:a", "aac",
            "-b:a", f"{self.preset['a']}k",
            "-movflags", "+faststart",
            "-loglevel", "error",
            "-progress", "pipe:1",
            "-nostats",
            outp
        ]

    def parse_progress_line(self, line, inp):
        try:
            if "out_time_ms=" in line:
                match = re.search(r'out_time_ms=(\d+)', line)
                if match:
                    current = int(match.group(1)) / 1_000_000  # ms → sec
                    total = self.total_durations.get(inp)

                    if total and total > 0:
                        return min(100.0, (current / total) * 100)

            if "progress=end" in line:
                return 100.0

        except Exception as e:
            logging.error(f"Progress error: {e}")

        return None

    def run(self):
        """main execution with pause/stop"""
        for i, file in enumerate(self.files):
            if self.stop_flag:
                break

            self.signals.status.emit(f"🔄 {i+1}/{len(self.files)} - {Path(file).name}")
            
            try:
                self.convert(file)
            except Exception as e:
                msg = f"❌ Error {Path(file).name}: {str(e)}"
                self.signals.status.emit(msg)
                logging.error(msg)

        self.signals.finished.emit()
        logging.info("Conversion finished")

    def convert(self, inp):
        """Conversion of file"""
        out = str(self.output_dir / f"{Path(inp).stem}.mp4")
        
        # Duration for progression
        self.get_duration(inp)
        
        process = None
        try:
            process = subprocess.Popen(
                self.build_cmd(inp, out),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='ignore'
            )

            self.process = process

            while True:
                if self.stop_flag:
                    process.kill()
                    return

                if self.paused:
                    time.sleep(0.1)
                    continue

                line = process.stdout.readline()

                if not line:
                    if process.poll() is not None:
                        break
                    time.sleep(0.01)
                    continue

                line = line.strip()
                progress = self.parse_progress_line(line, inp)

                if progress is not None:
                    self.signals.progress.emit(inp, progress)

            # Final wait
            try:
                process.wait(timeout=5)
                if process.returncode == 0 and Path(out).exists():
                    size = self.format_size(Path(out).stat().st_size)
                    self.signals.status.emit(f"✅ {Path(inp).name} OK ({size})")
                else:
                    self.signals.status.emit(f"❌ Error {Path(inp).name} (code: {process.returncode})")
            except subprocess.TimeoutExpired:
                process.kill()
                self.signals.status.emit(f"⏰ Timeout {Path(inp).name}")

        except Exception as e:
            msg = f"❌ Error conversion: {str(e)}"
            self.signals.status.emit(msg)
            logging.error(msg)
        finally:
            if process and process.poll() is None:
                try:
                    process.kill()
                    process.wait(timeout=5)
                except:
                    pass

    @staticmethod
    def format_size(size_bytes):
        if size_bytes > 1024**3:
            return f"{size_bytes/(1024**3):.1f} GB"
        return f"{size_bytes/(1024**2):.1f} MB"

# =========================================================
# UI QT
# =========================================================
class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PSP Video Converter")
        self.resize(950, 650)
        
        # Init
        self.files = []
        self.output_dir = Path.home() / "Videos" / "PSP"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.worker = None
        self.ffmpeg_ok = self.check_ffmpeg()
        
        if not self.ffmpeg_ok:
            self.show_ffmpeg_error()
            return

        self.setup_ui()
        self.cleanup_temp()

    def check_ffmpeg(self):
        """checks FFmpeg + log"""
        try:
            subprocess.run([FFMPEG_PATH, "-version"], 
                         capture_output=True, timeout=10, check=True)
            logging.info("FFmpeg OK")
            return True
        except Exception as e:
            logging.error(f"FFmpeg missing: {e}")
            return False

    def show_ffmpeg_error(self):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("❌ Error FFmpeg")
        msg.setText("FFmpeg missing !\n\n"
                   f"• Place the 'ffmpeg/' folder next to the executable\n"
                   f"• Contains ffmpeg.exe + ffprobe.exe\n\n"
                   f"Check psp_converter.log")
        msg.exec()

    def cleanup_temp(self):
        """cleans temp files"""
        temp_dir = Path(tempfile.gettempdir())
        for f in temp_dir.glob("psp_*.jpg"):
            try: f.unlink()
            except: pass

    def setup_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(15, 15, 15, 15)

        # TITLE
        title = QLabel("🎬 PSP Video Converter")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin: 10px; color: #4a90e2;")
        layout.addWidget(title)

        # INFO
        self.info_label = QLabel(f"📁 Out: {self.output_dir} | ✅ FFmpeg OK")
        self.info_label.setStyleSheet("font-size: 12px; color: #888; margin-bottom: 10px;")
        layout.addWidget(self.info_label)

        # TREE Drag & Drop
        self.tree = DraggableTreeWidget()
        self.tree.setHeaderLabels(["File", "Progress", "Size"])
        self.tree.setColumnWidth(0, 550)
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 180)
        self.tree.files_dropped.connect(self.add_dropped_files)
        layout.addWidget(self.tree)

        # BUTTONS
        row = QHBoxLayout()
        self.btn_add = QPushButton("➕ Add videos")
        self.btn_add.clicked.connect(self.add_files)

        self.btn_out = QPushButton("📁 Change output folder")
        self.btn_out.clicked.connect(self.choose_output)

        self.btn_clear = QPushButton("🗑️ Reset list")
        self.btn_clear.clicked.connect(self.clear_files)

        self.btn_start = QPushButton("🚀 Convert ALL")
        self.btn_start.clicked.connect(self.start_conversion)
        self.btn_start.setEnabled(self.ffmpeg_ok)

        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_pause.setEnabled(False)

        self.btn_stop = QPushButton("⛔ Stop")
        self.btn_stop.clicked.connect(self.stop_conversion)
        self.btn_stop.setEnabled(False)

        row.addWidget(self.btn_add)
        row.addWidget(self.btn_out)
        row.addWidget(self.btn_clear)
        row.addStretch()
        row.addWidget(self.btn_pause)
        row.addWidget(self.btn_stop)
        row.addWidget(self.btn_start)
        layout.addLayout(row)

        # OPTIONS
        options = QHBoxLayout()
        
        # Aspect group (exclusive selection)
        options.addWidget(QLabel("Aspect:"))
        self.aspect_group = QButtonGroup()
        self.keep_ratio = QRadioButton("🔒 Keep aspect (recommended)")
        self.keep_ratio.setChecked(True)
        self.stretch = QRadioButton("↔ Stretch")
        self.aspect_group.addButton(self.keep_ratio)
        self.aspect_group.addButton(self.stretch)
        options.addWidget(self.keep_ratio)
        options.addWidget(self.stretch)
        options.addStretch()
        
        # Quality Group (exclusive - only 1 selected)
        options.addWidget(QLabel("Quality:"))
        self.quality_group = QButtonGroup()
        self.preset_hq = QRadioButton("🟢 High")
        self.preset_mid = QRadioButton("🟡 Medium")
        self.preset_low = QRadioButton("🔴 Low size")
        self.preset_mid.setChecked(True)
        self.quality_group.addButton(self.preset_hq)
        self.quality_group.addButton(self.preset_mid)
        self.quality_group.addButton(self.preset_low)
        options.addWidget(self.preset_hq)
        options.addWidget(self.preset_mid)
        options.addWidget(self.preset_low)
        layout.addLayout(options)

        # PROGRESS GLOBAL
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # STATUS
        self.status_label = QLabel("🎉 Ready! Drag videos or click ➕")
        layout.addWidget(self.status_label)

        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #2c3e50, stop:1 #1a252f); 
            }
            QWidget { 
                background: transparent; 
                color: #ecf0f1; 
                font-family: 'Segoe UI', sans-serif; 
                font-size: 12px;
            }
            QLabel { 
                color: #bdc3c7; 
                padding: 8px; 
                background: rgba(0,0,0,0.1);
                border-radius: 4px;
            }
            QPushButton { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #3498db, stop:1 #2980b9);
                color: white; 
                padding: 10px 20px; 
                border-radius: 8px; 
                border: none; 
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #5dade2, stop:1 #3498db); 
            }
            QPushButton:pressed { background: #2c81c7; }
            QPushButton:disabled { 
                background: #7f8c8d; 
                color: #bdc3c7; 
            }
            QTreeWidget { 
                background: #34495e; 
                border: 2px solid #2c3e50; 
                border-radius: 8px;
                alternate-background-color: #3d566e;
                gridline-color: #2c3e50;
            }
            QTreeWidget::item { 
                padding: 12px; 
                border-bottom: 1px solid #2c3e50; 
            }
            QTreeWidget::item:selected { 
                background: #3498db; 
                color: white;
            }
            QTreeWidget::item:hover { 
                background: #5dade2; 
                color: white;
            }
            QHeaderView::section {
                background: #2c3e50;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QProgressBar { 
                border: 2px solid #3498db; 
                border-radius: 8px; 
                text-align: center; 
                color: white; 
                background: #2c3e50; 
                font-weight: bold;
                height: 30px;
            }
            QProgressBar::chunk { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2ecc71, stop:1 #27ae60); 
                border-radius: 6px;
            }
            QRadioButton {
                color: #ecf0f1;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
            QRadioButton::indicator:unchecked {
                border: 2px solid #7f8c8d;
                border-radius: 8px;
                background: #34495e;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #3498db;
                border-radius: 8px;
                background: #3498db;
            }
        """)

    # ---------------- FILES ----------------
    def add_dropped_files(self, files):
        added = 0
        for f in files:
            p = Path(f)
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS and f not in self.files:
                self.files.append(f)
                size = Converter.format_size(p.stat().st_size)
                item = QTreeWidgetItem([p.name, "0%", size])
                self.tree.addTopLevelItem(item)
                added += 1
        
        self.update_buttons()
        self.status_label.setText(f"✅ {added} video(s) added | Total: {len(self.files)}")

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select PSP Videos", 
            str(Path.home()),
            "Videos (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.mpg *.mpeg);;All files (*.*)"
        )
        self.add_dropped_files(files)

    def clear_files(self):
        self.tree.clear()
        self.files.clear()
        self.update_buttons()
        self.status_label.setText("🗑️ List cleared")

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(
            self, "PSP output folder", 
            str(self.output_dir)
        )
        if folder:
            self.output_dir = Path(folder)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.info_label.setText(f"📁 Output: {self.output_dir} | ✅ FFmpeg OK")
            self.status_label.setText(f"📁 Output folder changed: {self.output_dir}")

    def get_preset(self):
        """Returns selected preset"""
        if self.preset_hq.isChecked():
            return PRESETS["High quality"]
        elif self.preset_mid.isChecked():
            return PRESETS["Medium"]
        elif self.preset_low.isChecked():
            return PRESETS["Low size"]
        else:
            # Fallback
            logging.warning("No preset selected, using Medium")
            return PRESETS["Medium"]

    def get_aspect(self):
        """Returns selected aspect ratio"""
        return "keep" if self.keep_ratio.isChecked() else "stretch"

    def update_buttons(self):
        has_files = len(self.files) > 0
        self.btn_start.setEnabled(has_files and self.ffmpeg_ok)
        self.progress.setVisible(False)
        self.progress.setValue(0)

    # ---------------- CONVERSION ----------------
    def start_conversion(self):
        if not self.files or not self.ffmpeg_ok:
            return

        # Reset UI
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.status_label.setText("🚀 Conversion started...")

        # Signal Worker
        signals = Signals()

        # Connect
        signals.progress.connect(self.update_progress)
        signals.status.connect(self.update_status)
        signals.finished.connect(self.conversion_done)
        signals.pause_toggle.connect(self.on_pause_toggle)

        # Worker
        self.worker = Converter(
            self.files,
            signals,
            self.output_dir,
            self.get_aspect(),
            self.get_preset()
        )

        self.worker.start()
        

    def toggle_pause(self):
        if self.worker:
            with self.worker.mutex:
                self.worker.paused = not self.worker.paused

            # Worker
            self.worker.signals.pause_toggle.emit()

            if self.worker.paused:
                self.btn_pause.setText("▶ Resume")
                self.status_label.setText("⏸ PAUSE")
            else:
                self.btn_pause.setText("⏸ Pause")
                self.status_label.setText("▶ Resuming...")

    def stop_conversion(self):
        if not self.worker:
            return

        self.worker.stop_flag = True

        try:
            if hasattr(self.worker, "process") and self.worker.process:
                self.worker.process.kill()
        except Exception as e:
            logging.error(f"Stop error: {e}")

        self.status_label.setText("⛔ Stopping safely...")
        
    def update_progress(self, filename, value):
        total = self.tree.topLevelItemCount()
        if total == 0:
            return

        for i in range(total):
            item = self.tree.topLevelItem(i)
            if Path(filename).name == item.text(0):
                item.setText(1, f"{value:.1f}%{' ✅' if value >= 99.9 else ''}")
                break

        total_progress = 0
        done = 0

        for i in range(total):
            item = self.tree.topLevelItem(i)
            text = item.text(1)

            if "✅" in text:
                total_progress += 100
            else:
                try:
                    total_progress += float(text.replace("%", "").replace(" ", ""))
                except:
                    pass

            done += 1

        self.progress.setValue(int(total_progress / max(done, 1)))
        

    def update_status(self, text):
        self.status_label.setText(text)

    def on_pause_toggle(self):
        """Callback pause (empty - handled directly)"""
        pass

    def conversion_done(self):
        """Conversion complete"""
        self.btn_start.setEnabled(self.ffmpeg_ok)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ Pause")
        self.progress.setVisible(False)
        self.worker = None
        
        total = len(self.files)
        success = 0
        
        # Count the truly successful files
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            progress_text = item.text(1)
            filename = item.text(0)
            output_file = self.output_dir / f"{Path(filename).stem}.mp4"

            if progress_text.endswith('✅') or output_file.exists():
                success += 1
        
        self.status_label.setText(f"✅ Completed ! {success}/{total} OK 🎉")
        logging.info(f"Conversion completed: {success}/{total} successful")

# =========================================================
# DRAG & DROP
# =========================================================
class DraggableTreeWidget(QTreeWidget):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()

        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        self.setDragEnabled(False)
        self.setDragDropMode(QTreeWidget.DropOnly)
        self.setDropIndicatorShown(True)

        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).is_file():
                files.append(path)

        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()  # <-- important
        else:
            event.ignore()

# =========================================================
# RUN
# =========================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("PSP Video Converter")
    
    # Cache console Windows
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass
    
    window = App()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()