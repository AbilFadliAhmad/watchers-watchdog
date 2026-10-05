import os
import subprocess
import threading
import urllib.request
from service_logger import log_error, log_info

# --- STATE GLOBAL UNDUHAN ---
download_percentage = 0.0
is_downloading = False
download_lock = threading.Lock()

def run_background_silent_update(download_url: str):
    """Mendownload installer secara chunked dengan tracking persen.

    Mengabaikan eksekusi jika unduhan sedang berjalan.
    """
    global download_percentage, is_downloading

    # CEK & KUNCI STATE: Jangan ulangi jika sedang mendownload
    with download_lock:
        if is_downloading:
            log_info(
                "[UPDATE] Unduhan sedang berjalan. Mengabaikan perintah"
                " download ulang."
            )
            return
        is_downloading = True

    temp_dir = os.environ.get("TEMP", "C:\\Windows\\Temp")
    setup_path = os.path.join(temp_dir, "WatchersClient_Update.exe")

    try:
        log_info(f"[UPDATE] Memulai pengunduhan dari: {download_url}")
        req = urllib.request.urlopen(download_url)
        total_size = int(req.headers.get("Content-Length", 0))
        downloaded_size = 0
        chunk_size = 64 * 1024  # 64 KB

        with open(setup_path, "wb") as f:
            while True:
                chunk = req.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded_size += len(chunk)

                if total_size > 0:
                    # Hitung persentase desimal (misal: 45.5)
                    download_percentage = round(
                        (downloaded_size / total_size) * 100, 1
                    )

        log_info(
            "[UPDATE] Pengunduhan selesai (100%). Menjalankan installer..."
        )

        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000

        # Eksekusi installer secara detached
        subprocess.Popen(
            [setup_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True,
        )

    except Exception as e:
        log_error(f"[UPDATE ERROR] Gagal mengeksekusi silent update: {e}")
    finally:
        # Reset state setelah selesai atau jika terjadi error
        with download_lock:
            is_downloading = False
            download_percentage = 0.0