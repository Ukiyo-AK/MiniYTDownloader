#Для создания билда: pyinstaller --onefile --windowed --icon=icon.ico --add-data "azure.tcl;." --add-data "theme;theme" --name="YouTube Downloader V1.1" main.py


import os
import sys
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import yt_dlp
import requests
from mutagen.mp4 import MP4, MP4Cover

# --- Инициализация Tk и тема Azure ---
root = tk.Tk()
root.title("YouTube Downloader")
root.geometry("480x520")
root.resizable(False, False)

# Подключаем тему Azure и устанавливаем тёмную
root.tk.call("source", os.path.join(os.path.abspath(getattr(sys, '_MEIPASS', os.getcwd())), 'azure.tcl'))
current_theme = tk.StringVar(value="dark")
root.tk.call("set_theme", current_theme.get())

def toggle_theme():
    new_theme = "light" if current_theme.get() == "dark" else "dark"
    root.tk.call("set_theme", new_theme)
    current_theme.set(new_theme)

# --- Функция безопасного имени файла ---
def sanitize_filename(name):
    safe = re.sub(r"[^\w\- ]", "", name)
    return safe.strip()

# --- Хук прогресса и сбор путей скачанных файлов ---
_downloaded_audio = []  # список кортежей (filepath, info_dict)
def progress_hook(d):
    status = d.get('status')
    if status == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded = d.get('downloaded_bytes', 0)
        percent = (downloaded / total * 100) if total else float(d.get('_percent_str', '0').strip('%'))
        root.after(0, lambda p=percent: (
            progress_bar.config(value=p),
            progress_label.config(text=f"Загрузка: {p:.1f}%")
        ))
    elif status == 'finished':
        filename = d.get('filename')
        info = d.get('info_dict')
        if filename and filename.endswith('.m4a'):
            _downloaded_audio.append((filename, info))
        root.after(0, lambda: progress_label.config(text="Обработка..."))

# --- Функция встраивания метаданных в аудио ---
def embed_audio_metadata(filepath, info):
    try:
        audio = MP4(filepath)
        uploader = info.get('uploader') or info.get('channel')
        if uploader:
            audio['\xa9ART'] = uploader
        upload_date = info.get('upload_date')
        if upload_date and len(upload_date) >= 4:
            audio['\xa9day'] = upload_date[:4]
        thumbs = info.get('thumbnails') or []
        thumb_url = thumbs[0].get('url') if thumbs else info.get('thumbnail')
        if thumb_url:
            resp = requests.get(thumb_url)
            if resp.ok:
                fmt = MP4Cover.FORMAT_PNG if 'png' in resp.headers.get('Content-Type','') else MP4Cover.FORMAT_JPEG
                cover = MP4Cover(resp.content, imageformat=fmt)
                audio.tags['covr'] = [cover]
            else:
                print(f"Cover download failed: HTTP {resp.status_code}")
        else:
            print("No thumbnail URL available to embed cover.")
        audio.save()
    except Exception as e:
        print(f"Metadata embedding error: {e}")

# --- Функция загрузки ---
def download_video():
    url = url_entry.get().strip()
    path = path_var.get().strip()
    mode = mode_var.get()
    quality = quality_var.get()
    if not url or not path:
        messagebox.showerror("Ошибка", "Введите URL и папку для сохранения!")
        return
    fmt = 'best[ext=mp4]' if mode=='video' and quality=='Лучшее' else (
        'bestaudio[ext=m4a]' if mode=='audio' else (
            f"best[height<={quality.replace('p','')}][ext=mp4]"))
    outtmpl = os.path.join(path, '%(title)s.%(ext)s')
    ydl_opts = {
        'format': fmt,
        'outtmpl': outtmpl,
        'progress_hooks': [progress_hook],
        'ignoreerrors': True,
    }
    def run_download():
        try:
            _downloaded_audio.clear()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                ydl.download([url])
            if mode=='audio':
                for filepath, info in _downloaded_audio:
                    embed_audio_metadata(filepath, info)
            root.after(0, lambda: progress_label.config(text="✅ Загрузка завершена!"))
        except Exception as e:
            root.after(0, lambda: messagebox.showerror("Ошибка", str(e)))
    progress_bar['value'] = 0
    progress_label.config(text="Загрузка...")
    threading.Thread(target=run_download, daemon=True).start()

# --- Выбор папки ---
def choose_folder():
    folder = filedialog.askdirectory()
    if folder: path_var.set(folder)

# --- GUI ---
frame = ttk.Frame(root, padding=15)
frame.pack(fill=tk.BOTH, expand=True)

ttk.Button(frame, text="Переключить тему", command=toggle_theme).grid(row=0, column=2, sticky="e")

ttk.Label(frame, text="Ссылка на YouTube:").grid(row=1, column=0, sticky="w")
url_entry = ttk.Entry(frame, width=52)
url_entry.grid(row=2, column=0, columnspan=3, pady=5)

ttk.Label(frame, text="Папка для сохранения:").grid(row=3, column=0, sticky="w")
path_var = tk.StringVar()
ttk.Entry(frame, textvariable=path_var, width=40).grid(row=4, column=0, columnspan=2, pady=5, sticky="w")
ttk.Button(frame, text="Выбрать", command=choose_folder).grid(row=4, column=2)

mode_frame = ttk.LabelFrame(frame, text="Режим", padding=5)
mode_frame.grid(row=5, column=0, pady=10, sticky="w")
mode_var = tk.StringVar(value="video")
ttk.Radiobutton(mode_frame, text="Видео", variable=mode_var, value="video").pack(anchor="w")
ttk.Radiobutton(mode_frame, text="Аудио", variable=mode_var, value="audio").pack(anchor="w")

quality_frame = ttk.LabelFrame(frame, text="Качество", padding=5)
quality_frame.grid(row=5, column=1, padx=20, pady=10, sticky="w")
quality_var = tk.StringVar(value="720p")
for q in ["720p","480p","360p","Лучшее"]:
    ttk.Radiobutton(quality_frame, text=q, variable=quality_var, value=q).pack(anchor="w")

ttk.Button(frame, text="Скачать", command=download_video).grid(row=6, column=0, columnspan=3, pady=10)

progress_bar = ttk.Progressbar(frame, orient='horizontal', length=440, mode='determinate')
progress_bar.grid(row=7, column=0, columnspan=3, pady=5)
progress_label = ttk.Label(frame, text="", anchor="center")
progress_label.grid(row=8, column=0, columnspan=3)

root.mainloop()
