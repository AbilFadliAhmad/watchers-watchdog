import os
import subprocess
import threading
from timeit import main
import urllib.request
from service_logger import log_error, log_info
import hashlib

# --- STATE GLOBAL UNDUHAN ---
is_downloading = False
download_percentage = 0.0
download_lock = threading.Lock()

def run_background_silent_update(download_url: str, sha256_hash: str):
    """Mendownload installer secara chunked, memverifikasi integritas SHA-256,

    dan mengeksekusi installer secara silent jika verifikasi valid.
    """
    global is_downloading, download_percentage
    print(f"[UPDATE] Memulai proses update di background thread... {download_percentage}%")


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

        # Tambahkan User-Agent untuk menghindari pemblokiran HTTP 403 oleh server/Nginx/Cloudflare
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        req = urllib.request.Request(download_url, headers=headers)

        with urllib.request.urlopen(req) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded_size = 0
            chunk_size = 64 * 1024  # 64 KB

            # Inisialisasi hasher SHA-256
            hasher = hashlib.sha256()

            with open(setup_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break

                    f.write(chunk)
                    hasher.update(chunk)  # Hitung hash bersamaan saat stream
                    downloaded_size += len(chunk)

                    print(f"[UPDATE] Mengunduh: {downloaded_size}/{total_size} bytes")
                    if total_size > 0:
                        download_percentage = round(
                            (downloaded_size / total_size) * 100, 1
                        )  # Memperbarui persentase

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
        log_path = os.path.join(os.path.dirname(os.path.abspath(setup_path)), 'update.log')
        print(f"[UPDATE] Log update akan disimpan di: {log_path}")
        # Eksekusi installer secara detached
        subprocess.Popen(
            [setup_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={log_path}"],
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True,
        )
        print(f"[UPDATE] Installer dijalankan secara silent. Log update: {log_path}")

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