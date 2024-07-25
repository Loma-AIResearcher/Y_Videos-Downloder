
import os
import sys
import time
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QProgressBar, QCheckBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from pytube import Playlist, YouTube
import yt_dlp
import re

class FetchVideosThread(QThread):
    progress = pyqtSignal(str)

    def __init__(self, playlist_url):
        super().__init__()
        self.playlist_url = playlist_url

    def run(self):
        try:
            playlist = Playlist(self.playlist_url)
            # Ensure all videos are processed even if some requests fail
            self.video_titles = []
            self.video_urls = []
            for video in playlist.videos:
                try:
                    self.video_titles.append(video.title)
                    self.video_urls.append(video.watch_url)
                except Exception as e:
                    print(f"Error fetching video details: {e}")
            self.progress.emit("done")
        except Exception as e:
            self.progress.emit(f"error: {e}")

class DownloadVideoThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, video_url, download_path, resolution='720p'):
        super().__init__()
        self.video_url = video_url
        self.download_path = download_path
        self.resolution = resolution
        self._pause = False

    def run(self):
        try:
            ydl_opts = {
                'format': f'bestvideo[height<={self.resolution.replace("p", "")}]+bestaudio/best[height<={self.resolution.replace("p", "")}]',
                'outtmpl': os.path.join(self.download_path, '%(title)s.%(ext)s'),
                'noplaylist': True,
                'progress_hooks': [self.progress_hook],
                'continuedl': True,
                'nooverwrites': False,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.video_url])
            self.finished.emit("done")
        except Exception as e:
            self.progress.emit(f"error: {e}")
            self.finished.emit(f"error: {e}")
            print(f"Error downloading video: {e}")

    def progress_hook(self, d):
        while self._pause:
            time.sleep(0.5)

        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', None)

            progress = (downloaded_bytes / total_bytes) * 100 if total_bytes > 0 else 0
            downloaded_mb = downloaded_bytes / (1024 * 1024)
            total_mb = total_bytes / (1024 * 1024)
            speed_kib = speed / 1024 if speed else 0

            eta_str = f"{int(eta // 60):02d}:{int(eta % 60):02d}" if eta else "Unknown"
            progress_str = f"[download] {progress:.1f}% of {total_mb:.2f}MiB at {speed_kib:.2f}KiB/s ETA {eta_str}"
            self.progress.emit(progress_str)
        elif d['status'] == 'error':
            self.progress.emit(f"error: {d.get('error', 'Unknown error')}")

    def pause(self):
        self._pause = True

    def resume(self):
        self._pause = False

class YouTubeDownloaderApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('YouTube Downloader')
        self.setGeometry(100, 100, 600, 400)
        self.setFixedSize(600, 400)  # Make window unsizeable

        self.layout = QVBoxLayout()

        self.url_label = QLabel('Enter YouTube Playlist or Video URL:')
        self.layout.addWidget(self.url_label)

        self.url_entry = QLineEdit()
        self.url_entry.textChanged.connect(self.fetch_videos)  # Automatically fetch videos on URL change
        self.layout.addWidget(self.url_entry)

        self.download_folder_label = QLabel('Select Download Folder:')
        self.layout.addWidget(self.download_folder_label)

        self.download_folder_button = QPushButton('Browse')
        self.download_folder_button.clicked.connect(self.select_download_folder)
        self.layout.addWidget(self.download_folder_button)

        self.download_folder_display = QLabel('')
        self.layout.addWidget(self.download_folder_display)

        self.clear_list_button = QPushButton('Clear List')
        self.clear_list_button.clicked.connect(self.clear_video_list)
        self.layout.addWidget(self.clear_list_button)

        self.loading_label = QLabel('')
        self.layout.addWidget(self.loading_label)

        self.video_list_widget = QListWidget()
        self.video_list_widget.setSelectionMode(QListWidget.MultiSelection)
        self.layout.addWidget(self.video_list_widget)

        self.select_all_checkbox = QCheckBox('Select All')
        self.select_all_checkbox.stateChanged.connect(self.select_all_videos)
        self.layout.addWidget(self.select_all_checkbox)

        self.download_button = QPushButton('Download Selected')
        self.download_button.clicked.connect(self.download_selected)
        self.layout.addWidget(self.download_button)

        self.pause_button = QPushButton('Pause')
        self.pause_button.clicked.connect(self.pause_download)
        self.layout.addWidget(self.pause_button)

        self.progress_bar = QProgressBar()
        self.layout.addWidget(self.progress_bar)
        self.progress_bar.setVisible(False)

        self.progress_label = QLabel('')
        self.layout.addWidget(self.progress_label)

        self.setLayout(self.layout)

        self.download_folder = ''
        self.video_titles = []
        self.video_urls = []
        self.failed_downloads = []
        self.download_thread = None

    def select_download_folder(self):
        self.download_folder = QFileDialog.getExistingDirectory(self, 'Select Download Folder')
        self.download_folder_display.setText(self.download_folder)

    def fetch_videos(self):
        url = self.url_entry.text()
        if not url:
            return

        self.loading_label.setText('Fetching videos...')
        self.fetch_thread = FetchVideosThread(url)
        self.fetch_thread.progress.connect(self.on_fetch_progress)
        self.fetch_thread.start()

    def on_fetch_progress(self, status):
        if status == "done":
            self.loading_label.setText('')
            for title in self.fetch_thread.video_titles:
                if title not in [self.video_list_widget.item(i).text() for i in range(self.video_list_widget.count())]:
                    item = QListWidgetItem(title)
                    self.video_list_widget.addItem(item)
            self.video_titles.extend(self.fetch_thread.video_titles)
            self.video_urls.extend(self.fetch_thread.video_urls)
        elif status.startswith("error:"):
            self.loading_label.setText('')
            QMessageBox.critical(self, 'Error', status.replace("error:", "").strip())

    def select_all_videos(self, state):
        for i in range(self.video_list_widget.count()):
            item = self.video_list_widget.item(i)
            item.setSelected(state == Qt.Checked)

    def download_selected(self):
        if not self.download_folder:
            QMessageBox.critical(self, 'Error', 'Please select a download folder')
            return

        selected_items = self.video_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.critical(self, 'Error', 'No videos selected for download')
            return

        self.selected_urls = [self.video_urls[self.video_titles.index(item.text())] for item in selected_items]

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText('')
        self.failed_downloads = []

        self.current_download_index = 0
        self.download_next_video()

    def download_next_video(self):
        if self.current_download_index >= len(self.selected_urls):
            self.progress_bar.setVisible(False)
            if self.failed_downloads:
                QMessageBox.warning(self, 'Download Incomplete', f"Some videos failed to download:
{self.failed_downloads}")
            else:
                QMessageBox.information(self, 'Download Complete', 'All videos downloaded successfully!')
            return

        video_url = self.selected_urls[self.current_download_index]
        self.download_thread = DownloadVideoThread(video_url, self.download_folder)
        self.download_thread.progress.connect(self.on_download_progress)
        self.download_thread.finished.connect(self.on_download_finished)
        self.download_thread.start()

    def on_download_progress(self, progress_str):
        if progress_str.startswith("error:"):
            error_message = progress_str.replace("error:", "").strip()
            failed_video = self.video_titles[self.current_download_index]
            self.failed_downloads.append(f"{failed_video}: {error_message}")
            self.current_download_index += 1
            self.download_next_video()
        else:
            self.progress_label.setText(progress_str)
            try:
                progress = float(re.search(r'(\d+\.\d+)%', progress_str).group(1))
                self.progress_bar.setValue(int(progress))
            except Exception as e:
                self.progress_label.setText(f"Error parsing progress: {e}")

    def on_download_finished(self, status):
        if status.startswith("error:"):
            error_message = status.replace("error:", "").strip()
            failed_video = self.video_titles[self.current_download_index]
            self.failed_downloads.append(f"{failed_video}: {error_message}")
        self.current_download_index += 1
        self.download_next_video()

    def pause_download(self):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.pause()
            self.pause_button.setText('Resume')
            self.pause_button.clicked.disconnect()
            self.pause_button.clicked.connect(self.resume_download)

    def resume_download(self):
        if self.download_thread:
            self.download_thread.resume()
            self.pause_button.setText('Pause')
            self.pause_button.clicked.disconnect()
            self.pause_button.clicked.connect(self.pause_download)

    def clear_video_list(self):
        self.video_list_widget.clear()
        self.video_titles.clear()
        self.video_urls.clear()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = YouTubeDownloaderApp()
    window.show()
    sys.exit(app.exec_())

