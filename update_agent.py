import os
import subprocess
import threading
import urllib.request
from service_logger import log_error, log_info
import hashlib

# --- STATE GLOBAL UNDUHAN ---
download_percentage = 0.0
is_downloading = False
download_lock = threading.Lock()

def run_background_silent_update(download_url: str, sha256_hash: str):
    """Mendownload installer secara chunked, memverifikasi integritas SHA-256,

    dan mengeksekusi installer secara silent jika verifikasi valid.
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

        # Inisialisasi hasher SHA-256
        hasher = hashlib.sha256()

        with open(setup_path, "wb") as f:
            while True:
                chunk = req.read(chunk_size)
                if not chunk:
                    break

                f.write(chunk)
                hasher.update(chunk)  # Hitung hash secara bersamaan saat stream
                downloaded_size += len(chunk)

                if total_size > 0:
                    download_percentage = round(
                        (downloaded_size / total_size) * 100, 1
                    )

        # -----------------------------------------------------------------
        # VERIFIKASI INTEGRITAS SHA-256
        # -----------------------------------------------------------------
        calculated_sha256 = hasher.hexdigest().lower()
        expected_sha256 = sha256_hash.strip().lower() if sha256_hash else ""

        if expected_sha256 and calculated_sha256 != expected_sha256:
            log_error(
                f"[UPDATE ERROR] Verifikasi SHA-256 gagal!\n"
                f" - Expected : {expected_sha256}\n"
                f" - Actual   : {calculated_sha256}"
            )
            # Hapus file corrupt/tidak cocok untuk alasan keamanan
            if os.path.exists(setup_path):
                os.remove(setup_path)
            return

        log_info(
            f"[UPDATE] Pengunduhan & verifikasi SHA-256 berhasil"
            f" ({calculated_sha256[:10]}...). Menjalankan installer..."
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
        # Hapus file installer jika terjadi kegagalan jaringan atau parsing
        if os.path.exists(setup_path):
            try:
                os.remove(setup_path)
            except Exception:
                pass
    finally:
        # Reset state setelah selesai atau jika terjadi error
        with download_lock:
            is_downloading = False
            download_percentage = 0.0