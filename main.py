#Для сборки с встроенным ffmpeg:
#pyinstaller --onefile --windowed --icon=icon.ico --add-data "azure.tcl;." --add-data "theme;theme" --add-data "icon.ico;." --add-binary "ffmpeg\\ffmpeg.exe;ffmpeg" --add-binary "ffmpeg\\ffprobe.exe;ffmpeg" --name="MiniYTDownloader" main.py


import os
import sys
import re
import json
import time
import shutil
import io
from importlib import metadata as importlib_metadata
from urllib import request as urllib_request
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import threading
import requests
from packaging.version import parse as parse_version
from mutagen.mp4 import MP4, MP4Cover

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

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
root.title("MiniYTDownloader V1.3")
root.geometry("1040x640")
root.minsize(940, 560)
root.resizable(True, True)


# Иконка
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def resolve_ffmpeg_location():
    candidates = [
        os.path.join(resource_path("ffmpeg"), "ffmpeg.exe"),
        os.path.join(os.path.dirname(sys.executable), "ffmpeg", "ffmpeg.exe"),
        os.path.join(os.path.abspath("."), "ffmpeg", "ffmpeg.exe"),
    ]
    for ffmpeg_exe in candidates:
        if os.path.isfile(ffmpeg_exe):
            return os.path.dirname(ffmpeg_exe)
    return None


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
    os.path.join(os.path.abspath(getattr(sys, "_MEIPASS", os.getcwd())), "azure.tcl")
)
current_theme = tk.StringVar(value="dark")
root.tk.call("set_theme", current_theme.get())


def toggle_theme():
    new_theme = "light" if current_theme.get() == "dark" else "dark"
    root.tk.call("set_theme", new_theme)
    current_theme.set(new_theme)


def sanitize_filename(name):
    safe = re.sub(r"[^\w\- ]", "", name)
    return safe.strip()


def shorten_text(text, max_len=70):
    normalized = str(text or "").replace("\n", " ").strip()
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 1].rstrip() + "..."


def pick_thumbnail_url(info):
    if not isinstance(info, dict):
        return None
    thumbs = info.get("thumbnails") or []
    valid = [item for item in thumbs if isinstance(item, dict) and item.get("url")]
    if valid:
        valid.sort(key=lambda t: (t.get("width") or 0) * (t.get("height") or 0), reverse=True)
        return valid[0].get("url")
    return info.get("thumbnail")


def extract_display_title(info, fallback):
    if not isinstance(info, dict):
        return fallback
    title = info.get("title")
    if title:
        return title
    if info.get("_type") == "playlist":
        playlist_title = info.get("title") or "Плейлист"
        return f"{playlist_title} (плейлист)"
    return fallback


def render_thumbnail_from_bytes(image_bytes):
    if Image is None or ImageTk is None:
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
            img.thumbnail((96, 54), resample)
            canvas = Image.new("RGB", (96, 54), color=(16, 16, 16))
            x = (96 - img.width) // 2
            y = (54 - img.height) // 2
            canvas.paste(img, (x, y))
            return ImageTk.PhotoImage(canvas)
    except Exception:
        return None


# --- Состояние очереди загрузки ---
_downloaded_audio = []  # список кортежей (filepath, info_dict)
_download_state = {"current": 1, "total": 1}
_download_rows = {}
_download_meta = {}
_download_thumbnails = {}
_download_in_progress = False


def refresh_queue_summary():
    total = len(_download_rows)
    if total == 0:
        queue_summary_var.set("Очередь пуста")
        return

    done = 0
    failed = 0
    active = 0
    for item_id in _download_rows.values():
        values = list(downloads_tree.item(item_id, "values") or [])
        status = values[1] if len(values) > 1 else ""
        if status == "Готово":
            done += 1
        elif str(status).startswith("Ошибка"):
            failed += 1
        elif status and status != "Ожидание":
            active += 1

    queue_summary_var.set(f"Всего: {total} | Готово: {done} | Ошибки: {failed} | В процессе: {active}")


def clear_download_queue():
    for item_id in downloads_tree.get_children():
        downloads_tree.delete(item_id)
    _download_rows.clear()
    _download_meta.clear()
    _download_thumbnails.clear()
    refresh_queue_summary()


def add_download_queue_item(task_index, source_url, mode):
    kind_label = "Видео" if mode == "video" else "Аудио"
    row_text = f"{task_index}. {shorten_text(source_url, 64)}"
    item_id = downloads_tree.insert("", tk.END, text=row_text, values=(kind_label, "Ожидание", "0%"))
    _download_rows[task_index] = item_id
    _download_meta[task_index] = {
        "title": source_url,
        "kind": kind_label,
        "thumbnail_requested": False,
    }
    refresh_queue_summary()


def apply_thumbnail_image(task_index, image_bytes):
    item_id = _download_rows.get(task_index)
    if not item_id:
        return
    photo = render_thumbnail_from_bytes(image_bytes)
    if photo is None:
        return
    _download_thumbnails[task_index] = photo
    downloads_tree.item(item_id, image=photo)


def load_thumbnail_async(task_index, thumb_url):
    if not thumb_url or Image is None or ImageTk is None:
        return

    def _worker():
        try:
            resp = requests.get(thumb_url, timeout=10)
            resp.raise_for_status()
            root.after(0, apply_thumbnail_image, task_index, resp.content)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def update_download_queue_item(task_index, title=None, status=None, progress=None, info_dict=None):
    item_id = _download_rows.get(task_index)
    if not item_id:
        return

    meta = _download_meta.setdefault(
        task_index,
        {"title": title or f"Элемент {task_index}", "kind": "Видео", "thumbnail_requested": False},
    )

    if title:
        meta["title"] = title

    if info_dict and not meta.get("thumbnail_requested"):
        thumb_url = pick_thumbnail_url(info_dict)
        if thumb_url:
            meta["thumbnail_requested"] = True
            load_thumbnail_async(task_index, thumb_url)

    row_text = f"{task_index}. {shorten_text(meta['title'], 64)}"
    current_values = list(downloads_tree.item(item_id, "values") or [meta["kind"], "", ""])
    while len(current_values) < 3:
        current_values.append("")
    if status is not None:
        current_values[1] = status
    if progress is not None:
        current_values[2] = progress

    downloads_tree.item(item_id, text=row_text, values=tuple(current_values))
    refresh_queue_summary()


def set_controls_for_download(is_running):
    global _download_in_progress
    _download_in_progress = is_running

    state = tk.DISABLED if is_running else tk.NORMAL
    for widget in [url_text, path_entry, choose_button, theme_button, download_button]:
        widget.config(state=state)
    for radio in mode_radios + quality_radios:
        radio.config(state=state)

    if is_running:
        embed_check.config(state=tk.DISABLED)
    else:
        update_embed_state()


def parse_percent_from_hook(payload):
    total = payload.get("total_bytes") or payload.get("total_bytes_estimate")
    downloaded = payload.get("downloaded_bytes", 0)
    if total:
        return max(0.0, min(100.0, (downloaded / total) * 100))
    raw_percent = str(payload.get("_percent_str", "0")).replace("%", "").replace(",", ".").strip()
    try:
        return max(0.0, min(100.0, float(raw_percent)))
    except Exception:
        return 0.0


def progress_hook(d):
    status = d.get("status")
    current_index = _download_state.get("current", 1)
    total_items = max(1, _download_state.get("total", 1))
    info = d.get("info_dict") or {}
    title = info.get("title")

    if status == "downloading":
        percent = parse_percent_from_hook(d)
        root.after(0, lambda p=percent, i=current_index, t=total_items: (
            progress_bar.config(value=p),
            progress_label.config(text=f"Загрузка {i}/{t}: {p:.1f}%")
        ))
        root.after(
            0,
            update_download_queue_item,
            current_index,
            title,
            "Скачивание",
            f"{percent:.1f}%",
            info,
        )
    elif status == "finished":
        filename = d.get("filename")
        if filename and filename.lower().endswith(".m4a"):
            _downloaded_audio.append((filename, info))
        root.after(0, lambda i=current_index, t=total_items: progress_label.config(text=f"Обработка {i}/{t}..."))
        root.after(0, update_download_queue_item, current_index, title, "Обработка", "100%", info)
    elif status == "error":
        root.after(0, update_download_queue_item, current_index, title, "Ошибка", "-", info)


def embed_audio_metadata(filepath, info):
    try:
        audio = MP4(filepath)
        uploader = info.get("uploader") or info.get("channel")
        if uploader:
            audio["\xa9ART"] = uploader
        upload_date = info.get("upload_date")
        if upload_date and len(upload_date) >= 4:
            audio["\xa9day"] = upload_date[:4]
        thumbs = info.get("thumbnails") or []
        thumb_url = thumbs[0].get("url") if thumbs else info.get("thumbnail")
        if thumb_url:
            resp = requests.get(thumb_url, timeout=10)
            if resp.ok:
                content_type = resp.headers.get("Content-Type", "")
                fmt = MP4Cover.FORMAT_PNG if "png" in content_type else MP4Cover.FORMAT_JPEG
                cover = MP4Cover(resp.content, imageformat=fmt)
                audio.tags["covr"] = [cover]
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


def finish_download_session(total_urls, failed_count):
    success_count = max(0, total_urls - failed_count)
    progress_bar.config(value=100)
    if failed_count:
        progress_label.config(text=f"Завершено: {success_count}/{total_urls}. Ошибок: {failed_count}.")
    else:
        progress_label.config(text=f"✅ Загрузка завершена: {success_count} шт.")
    set_controls_for_download(False)


def download_video():
    if _download_in_progress:
        messagebox.showwarning("Загрузка уже идёт", "Дождитесь завершения текущей очереди.")
        return

    urls = parse_input_urls()
    path = path_var.get().strip()
    mode = mode_var.get()
    quality = quality_var.get()
    embed = embed_var.get()

    if not urls or not path:
        messagebox.showerror("Ошибка", "Введите хотя бы один URL и папку для сохранения!")
        return

    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось создать папку:\n{e}")
        return

    clear_download_queue()
    for index, source_url in enumerate(urls, start=1):
        add_download_queue_item(index, source_url, mode)

    bundled_ffmpeg_location = resolve_ffmpeg_location()
    can_merge_streams = bool(bundled_ffmpeg_location or shutil.which("ffmpeg") or shutil.which("ffmpeg.exe"))

    if mode == "video":
        fmt = build_video_format(quality, can_merge_streams)
        if quality == "1080p" and not can_merge_streams:
            messagebox.showwarning(
                "Ограничение 1080p",
                "Для полноценного 1080p нужен ffmpeg. Сейчас будет загружен лучший доступный mp4 без склейки дорожек.",
            )
    else:
        fmt = "bestaudio[ext=m4a]"

    outtmpl = os.path.join(path, "%(title)s.%(ext)s")
    ydl_opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "progress_hooks": [progress_hook],
        "ignoreerrors": True,
    }
    if bundled_ffmpeg_location:
        ydl_opts["ffmpeg_location"] = bundled_ffmpeg_location
    if mode == "video" and can_merge_streams:
        ydl_opts["merge_output_format"] = "mp4"

    progress_bar["value"] = 0
    progress_label.config(text=f"Загрузка 1/{len(urls)}...")
    set_controls_for_download(True)

    def run_download():
        failed_count = 0
        try:
            _downloaded_audio.clear()
            _download_state["total"] = len(urls)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for index, source_url in enumerate(urls, start=1):
                    _download_state["current"] = index
                    root.after(0, update_download_queue_item, index, None, "Получение данных", "0%", None)

                    info = None
                    try:
                        info = ydl.extract_info(source_url, download=False)
                        display_title = extract_display_title(info, source_url)
                        root.after(0, update_download_queue_item, index, display_title, "Ожидание", "0%", info)
                    except Exception:
                        pass

                    exit_code = ydl.download([source_url])
                    if exit_code in (0, None):
                        root.after(0, update_download_queue_item, index, None, "Готово", "100%", info)
                    else:
                        failed_count += 1
                        root.after(0, update_download_queue_item, index, None, "Ошибка", "-", info)

            if mode == "audio" and embed and _downloaded_audio:
                root.after(0, lambda: progress_label.config(text="Встраивание обложек в аудио..."))
                for filepath, info in _downloaded_audio:
                    embed_audio_metadata(filepath, info)

        except Exception as e:
            failed_count = len(urls)
            root.after(0, lambda err=str(e): messagebox.showerror("Ошибка", err))
        finally:
            _download_state["current"] = 1
            _download_state["total"] = 1
            root.after(0, finish_download_session, len(urls), failed_count)

    threading.Thread(target=run_download, daemon=True).start()


def choose_folder():
    folder = filedialog.askdirectory()
    if folder:
        path_var.set(folder)


# --- GUI ---
main_frame = ttk.Frame(root, padding=12)
main_frame.pack(fill=tk.BOTH, expand=True)
main_frame.columnconfigure(0, weight=3)
main_frame.columnconfigure(1, weight=2)
main_frame.rowconfigure(0, weight=1)

left_panel = ttk.Frame(main_frame)
left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
left_panel.columnconfigure(0, weight=1)
left_panel.columnconfigure(1, weight=0)
left_panel.columnconfigure(2, weight=0)
left_panel.rowconfigure(2, weight=1)

right_panel = ttk.LabelFrame(main_frame, text="Текущие загрузки", padding=10)
right_panel.grid(row=0, column=1, sticky="nsew")
right_panel.columnconfigure(0, weight=1)
right_panel.rowconfigure(2, weight=1)

ttk.Label(left_panel, text="MiniYTDownloader", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
theme_button = ttk.Button(left_panel, text="Тема", command=toggle_theme)
theme_button.grid(row=0, column=2, sticky="e")

ttk.Label(left_panel, text="Ссылки на YouTube (по одной в строке):").grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
url_text = tk.Text(left_panel, width=56, height=8, wrap="word")
url_text.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(6, 10))

ttk.Label(left_panel, text="Папка для сохранения:").grid(row=3, column=0, columnspan=3, sticky="w")
path_var = tk.StringVar()
path_entry = ttk.Entry(left_panel, textvariable=path_var, width=45)
path_entry.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 10))
choose_button = ttk.Button(left_panel, text="Выбрать", command=choose_folder)
choose_button.grid(row=4, column=2, padx=(8, 0), pady=(6, 10))

mode_frame = ttk.LabelFrame(left_panel, text="Режим", padding=8)
mode_frame.grid(row=5, column=0, sticky="nw")
mode_var = tk.StringVar(value="video")
mode_radios = []
video_radio = ttk.Radiobutton(mode_frame, text="Видео", variable=mode_var, value="video")
audio_radio = ttk.Radiobutton(mode_frame, text="Аудио", variable=mode_var, value="audio")
video_radio.pack(anchor="w")
audio_radio.pack(anchor="w")
mode_radios.extend([video_radio, audio_radio])

quality_frame = ttk.LabelFrame(left_panel, text="Качество", padding=8)
quality_frame.grid(row=5, column=1, padx=12, sticky="nw")
quality_var = tk.StringVar(value="720p")
quality_radios = []
for q in ["1080p", "720p", "480p", "360p", "Лучшее"]:
    radio = ttk.Radiobutton(quality_frame, text=q, variable=quality_var, value=q)
    radio.pack(anchor="w")
    quality_radios.append(radio)

embed_var = tk.BooleanVar(value=True)


def on_embed_toggle():
    state = "Включено" if embed_var.get() else "Выключено"
    progress_label.config(text=f"Встраивание обложки: {state}")


embed_check = tk.Checkbutton(
    left_panel,
    text="Встраивать обложку в аудио",
    variable=embed_var,
    onvalue=True,
    offvalue=False,
    command=on_embed_toggle,
)
embed_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 8))

download_button = ttk.Button(left_panel, text="Скачать", command=download_video)
download_button.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 10))

progress_bar = ttk.Progressbar(left_panel, orient="horizontal", mode="determinate")
progress_bar.grid(row=8, column=0, columnspan=3, sticky="ew")
progress_label = ttk.Label(left_panel, text="", anchor="center")
progress_label.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(6, 0))

queue_summary_var = tk.StringVar(value="Очередь пуста")
ttk.Label(right_panel, textvariable=queue_summary_var).grid(row=0, column=0, sticky="w")
ttk.Label(right_panel, text="Здесь отображаются текущие и завершённые задачи этого запуска.").grid(
    row=1, column=0, sticky="w", pady=(2, 8)
)

style = ttk.Style()
style.configure("Queue.Treeview", rowheight=68)

tree_wrap = ttk.Frame(right_panel)
tree_wrap.grid(row=2, column=0, sticky="nsew")
tree_wrap.columnconfigure(0, weight=1)
tree_wrap.rowconfigure(0, weight=1)

downloads_tree = ttk.Treeview(
    tree_wrap,
    columns=("kind", "status", "progress"),
    show="tree headings",
    style="Queue.Treeview",
)
downloads_tree.heading("#0", text="Ролик / Аудио")
downloads_tree.heading("kind", text="Тип")
downloads_tree.heading("status", text="Статус")
downloads_tree.heading("progress", text="Прогресс")
downloads_tree.column("#0", width=290, anchor="w", stretch=True)
downloads_tree.column("kind", width=68, anchor="center", stretch=False)
downloads_tree.column("status", width=100, anchor="center", stretch=False)
downloads_tree.column("progress", width=72, anchor="center", stretch=False)
downloads_tree.grid(row=0, column=0, sticky="nsew")

tree_scrollbar = ttk.Scrollbar(tree_wrap, orient="vertical", command=downloads_tree.yview)
tree_scrollbar.grid(row=0, column=1, sticky="ns")
downloads_tree.configure(yscrollcommand=tree_scrollbar.set)


def update_embed_state(*args):
    if _download_in_progress:
        embed_check.config(state=tk.DISABLED)
        return
    if mode_var.get() == "audio":
        embed_check.config(state=tk.NORMAL)
    else:
        embed_check.config(state=tk.DISABLED)


mode_var.trace_add("write", update_embed_state)
update_embed_state()
clear_download_queue()

root.mainloop()
