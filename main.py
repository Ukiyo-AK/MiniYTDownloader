#Для создания сборки: pyinstaller --onefile --windowed --icon=icon.ico --add-data "azure.tcl;." --add-data "theme;theme" --name="MiniYTDownloader" main.py


import os
import sys
import re
import json
import time
import shutil
from importlib import metadata as importlib_metadata
from urllib import request as urllib_request
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import threading
import requests
from packaging.version import parse as parse_version
from mutagen.mp4 import MP4, MP4Cover

APP_NAME = "MiniYTDownloader"
YT_DLP_PYPI_JSON_URL = "https://pypi.org/pypi/yt-dlp/json"
YT_DLP_CHECK_INTERVAL_SECONDS = 12 * 60 * 60


def _get_runtime_dir():
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    runtime_dir = os.path.join(local_app_data, APP_NAME, "runtime")
    os.makedirs(runtime_dir, exist_ok=True)
    return runtime_dir


def _load_state(state_path):
    if not os.path.isfile(state_path):
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        if isinstance(state, dict):
            return state
    except Exception:
        pass
    return {}


def _save_state(state_path, state):
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _prepend_sys_path(path):
    if not path:
        return
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)


def _distribution_version(package_name, default="0"):
    try:
        return importlib_metadata.version(package_name)
    except Exception:
        return default


def _fetch_latest_yt_dlp_release(timeout=6):
    req = urllib_request.Request(
        YT_DLP_PYPI_JSON_URL,
        headers={"User-Agent": f"{APP_NAME} yt-dlp-updater"},
    )
    with urllib_request.urlopen(req, timeout=timeout) as response:
        data = json.load(response)

    latest_version = (data.get("info") or {}).get("version")
    if not latest_version:
        return None, None

    release_files = (data.get("releases") or {}).get(latest_version, [])
    if not release_files:
        release_files = data.get("urls") or []

    wheel_url = None
    for file_info in release_files:
        filename = file_info.get("filename", "")
        if file_info.get("packagetype") == "bdist_wheel" and filename.endswith("py3-none-any.whl"):
            wheel_url = file_info.get("url")
            break

    if not wheel_url:
        for file_info in release_files:
            url = file_info.get("url", "")
            if url.endswith(".whl"):
                wheel_url = url
                break

    return latest_version, wheel_url


def _download_file(url, target_path, timeout=30):
    tmp_path = f"{target_path}.tmp"
    req = urllib_request.Request(url, headers={"User-Agent": f"{APP_NAME} yt-dlp-updater"})
    try:
        with urllib_request.urlopen(req, timeout=timeout) as response, open(tmp_path, "wb") as f:
            shutil.copyfileobj(response, f)
        os.replace(tmp_path, target_path)
    finally:
        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _version_is_newer(candidate_version, current_version):
    try:
        return parse_version(candidate_version) > parse_version(current_version)
    except Exception:
        return candidate_version != current_version


def _version_is_at_least(candidate_version, baseline_version):
    try:
        return parse_version(candidate_version) >= parse_version(baseline_version)
    except Exception:
        return candidate_version == baseline_version


def prepare_yt_dlp_runtime():
    runtime_dir = _get_runtime_dir()
    state_path = os.path.join(runtime_dir, "yt_dlp_update_state.json")
    state = _load_state(state_path)

    bundled_version = _distribution_version("yt-dlp")
    active_version = bundled_version

    cached_wheel_path = state.get("wheel_path")
    cached_version = state.get("version", "0")
    use_cached_wheel = (
        cached_wheel_path
        and os.path.isfile(cached_wheel_path)
        and _version_is_at_least(cached_version, bundled_version)
    )
    if use_cached_wheel:
        _prepend_sys_path(cached_wheel_path)
        active_version = cached_version

    now_ts = int(time.time())
    last_check = int(state.get("last_check", 0) or 0)
    if now_ts - last_check < YT_DLP_CHECK_INTERVAL_SECONDS:
        return

    state["last_check"] = now_ts
    try:
        latest_version, wheel_url = _fetch_latest_yt_dlp_release()
        if not latest_version or not wheel_url:
            return

        if not _version_is_newer(latest_version, active_version):
            state["version"] = active_version
            return

        wheel_filename = f"yt_dlp-{latest_version}-py3-none-any.whl"
        wheel_path = os.path.join(runtime_dir, wheel_filename)
        _download_file(wheel_url, wheel_path)

        for filename in os.listdir(runtime_dir):
            is_old_wheel = filename.startswith("yt_dlp-") and filename.endswith(".whl") and filename != wheel_filename
            if is_old_wheel:
                try:
                    os.remove(os.path.join(runtime_dir, filename))
                except OSError:
                    pass

        state["version"] = latest_version
        state["wheel_path"] = wheel_path
        _prepend_sys_path(wheel_path)
    except Exception as e:
        print(f"yt-dlp auto-update skipped: {e}")
    finally:
        _save_state(state_path, state)


prepare_yt_dlp_runtime()
import yt_dlp

# --- Инициализация Tk и тема Azure ---
root = tk.Tk()
root.title("MiniYTDownloader V1.2.1")
root.geometry("560x530")  # увеличено для мультизагрузки
root.resizable(False, False)

# Иконка
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

_icon_path = resource_path("icon.ico")

try:
    if _icon_path.lower().endswith(".ico") and sys.platform.startswith("win"):
        root.iconbitmap(_icon_path)
    else:
        _img = tk.PhotoImage(file=_icon_path)
        root.iconphoto(True, _img)
        root._icon_img = _img
except Exception as e:
    print("Не удалось установить иконку окна:", e)

# Подключаем тему Azure и устанавливаем тёмную
root.tk.call(
    "source",
    os.path.join(os.path.abspath(getattr(sys, '_MEIPASS', os.getcwd())), 'azure.tcl')
)
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

# --- Хук прогресса и сбор путей скачанных аудио ---
_downloaded_audio = []  # список кортежей (filepath, info_dict)
_download_state = {"current": 1, "total": 1}


def progress_hook(d):
    status = d.get('status')
    current_index = _download_state.get("current", 1)
    total_items = max(1, _download_state.get("total", 1))
    if status == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded = d.get('downloaded_bytes', 0)
        percent = (downloaded / total * 100) if total else float(d.get('_percent_str', '0').strip('%'))
        root.after(0, lambda p=percent, i=current_index, t=total_items: (
            progress_bar.config(value=p),
            progress_label.config(text=f"Загрузка {i}/{t}: {p:.1f}%")
        ))
    elif status == 'finished':
        filename = d.get('filename')
        info = d.get('info_dict')
        if filename and filename.lower().endswith('.m4a'):
            _downloaded_audio.append((filename, info))
        root.after(0, lambda i=current_index, t=total_items: progress_label.config(text=f"Обработка {i}/{t}..."))

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


def parse_input_urls():
    raw_text = url_text.get("1.0", tk.END).strip()
    if not raw_text:
        return []

    parts = re.split(r"[\s,;]+", raw_text)
    urls = []
    seen = set()
    for part in parts:
        item = part.strip()
        if not item or item in seen:
            continue
        urls.append(item)
        seen.add(item)
    return urls


def build_video_format(quality, can_merge_streams):
    quality_map = {
        "1080p": 1080,
        "720p": 720,
        "480p": 480,
        "360p": 360,
    }

    if quality == "Лучшее":
        if can_merge_streams:
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best"
        return "best[ext=mp4]/best"

    max_height = quality_map.get(quality, 720)
    if can_merge_streams:
        return (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}][ext=mp4]/best[height<={max_height}]"
        )
    return f"best[height<={max_height}][ext=mp4]/best[height<={max_height}]"


# --- Функция загрузки ---
def download_video():
    urls = parse_input_urls()
    path = path_var.get().strip()
    mode = mode_var.get()
    quality = quality_var.get()
    embed = embed_var.get()

    if not urls or not path:
        messagebox.showerror("Ошибка", "Введите хотя бы один URL и папку для сохранения!")
        return

    can_merge_streams = bool(shutil.which("ffmpeg") or shutil.which("ffmpeg.exe"))

    # выбор формата
    if mode == 'video':
        fmt = build_video_format(quality, can_merge_streams)
        if quality == "1080p" and not can_merge_streams:
            messagebox.showwarning(
                "Ограничение 1080p",
                "Для полноценного 1080p нужен ffmpeg. Сейчас будет загружен лучший доступный mp4 без склейки дорожек."
            )
    else:
        fmt = 'bestaudio[ext=m4a]'

    outtmpl = os.path.join(path, '%(title)s.%(ext)s')
    ydl_opts = {
        'format': fmt,
        'outtmpl': outtmpl,
        'progress_hooks': [progress_hook],
        'ignoreerrors': True,
    }
    if mode == 'video' and can_merge_streams:
        ydl_opts['merge_output_format'] = 'mp4'

    def run_download():
        try:
            _downloaded_audio.clear()
            _download_state["total"] = len(urls)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for index, url in enumerate(urls, start=1):
                    _download_state["current"] = index
                    ydl.download([url])
            if mode == 'audio' and embed:
                for filepath, info in _downloaded_audio:
                    embed_audio_metadata(filepath, info)
            root.after(0, lambda total=len(urls): progress_label.config(text=f"✅ Загрузка завершена: {total} шт."))
        except Exception as e:
            root.after(0, lambda: messagebox.showerror("Ошибка", str(e)))
        finally:
            _download_state["current"] = 1
            _download_state["total"] = 1

    progress_bar['value'] = 0
    progress_label.config(text=f"Загрузка 1/{len(urls)}...")
    threading.Thread(target=run_download, daemon=True).start()

# --- Выбор папки ---
def choose_folder():
    folder = filedialog.askdirectory()
    if folder:
        path_var.set(folder)

# --- GUI ---
frame = ttk.Frame(root, padding=15)
frame.pack(fill=tk.BOTH, expand=True)

ttk.Button(frame, text="Переключить тему", command=toggle_theme).grid(row=0, column=2, sticky="e")

ttk.Label(frame, text="Ссылки на YouTube (по одной в строке):").grid(row=1, column=0, sticky="w")
url_text = tk.Text(frame, width=52, height=4, wrap="word")
url_text.grid(row=2, column=0, columnspan=3, pady=5)

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
for q in ["1080p", "720p", "480p", "360p", "Лучшее"]:
    ttk.Radiobutton(quality_frame, text=q, variable=quality_var, value=q).pack(anchor="w")

# --- Чекбокс встраивания превью для аудио ---
embed_var = tk.BooleanVar(value=True)

def on_embed_toggle():
    # краткое сообщение в GUI для обратной связи (можно убрать)
    state = "Включено" if embed_var.get() else "Выключено"
    progress_label.config(text=f"Встраивание обложки: {state}")

# используем tk.Checkbutton — он обычно надёжнее в темах
embed_check = tk.Checkbutton(
    frame,
    text="Встраивать обложку в аудио",
    variable=embed_var,
    onvalue=True,
    offvalue=False,
    command=on_embed_toggle
)
embed_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=5)

# делаем чекбокс доступным только в режиме 'audio'
def update_embed_state(*args):
    if mode_var.get() == 'audio':
        embed_check.config(state=tk.NORMAL)
    else:
        embed_check.config(state=tk.DISABLED)
# привязываем следение к изменениям режима
mode_var.trace_add('write', update_embed_state)
# вызвать один раз, чтобы установить начальное состояние
update_embed_state()

# Кнопка скачать
ttk.Button(frame, text="Скачать", command=download_video).grid(row=7, column=0, columnspan=3, pady=10)

# Прогрессбар и метка
progress_bar = ttk.Progressbar(frame, orient='horizontal', length=440, mode='determinate')
progress_bar.grid(row=8, column=0, columnspan=3, pady=5)
progress_label = ttk.Label(frame, text="", anchor="center")
progress_label.grid(row=9, column=0, columnspan=3)

root.mainloop()
