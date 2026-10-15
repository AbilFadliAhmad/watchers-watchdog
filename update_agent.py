from datetime import datetime
import hashlib
import os
import subprocess
import threading
import urllib.request
from service_logger import log_error, log_info

is_downloading = False
download_percentage = 0.0
download_lock = threading.Lock()


def run_background_silent_update(download_url: str, sha256_hash: str):
    global is_downloading, download_percentage

    with download_lock:
        if is_downloading:
            log_info(
                "[UPDATE] Unduhan sedang berjalan. Mengabaikan perintah"
                " download ulang."
            )
            return
        is_downloading = True

    # 1. Samakan Timestamp untuk Nama Installer & File Log
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    base_programdata = os.environ.get("ProgramData", r"C:\ProgramData")
    temp_dir = os.environ.get("TEMP", r"C:\Windows\Temp")

    setup_path = os.path.join(temp_dir, f"WatchersAgent_{timestamp}.exe")
    log_path = os.path.join(base_programdata, f"watchers_update_{timestamp}.log")
    app_dir = os.path.join(base_programdata, "WatchersAgent")
    uninstaller_path = os.path.join(app_dir, "unins000.exe")

    try:
        log_info(f"[UPDATE] Memulai pengunduhan dari: {download_url}")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        req = urllib.request.Request(download_url, headers=headers)

        # 2. Unduh Langsung ke setup_path yang Sudah Didefinisikan
        with urllib.request.urlopen(req) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded_size = 0
            chunk_size = 64 * 1024
            hasher = hashlib.sha256()

            with open(setup_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded_size += len(chunk)

                    if total_size > 0:
                        download_percentage = round(
                            (downloaded_size / total_size) * 100, 1
                        )

        # 3. Verifikasi Integrity SHA-256
        calculated_sha256 = hasher.hexdigest().lower()
        expected_sha256 = sha256_hash.strip().lower() if sha256_hash else ""

        if expected_sha256 and calculated_sha256 != expected_sha256:
            log_error(
                f"[UPDATE ERROR] Verifikasi SHA-256 gagal!\n"
                f" - Expected : {expected_sha256}\n"
                f" - Actual   : {calculated_sha256}"
            )
            if os.path.exists(setup_path):
                os.remove(setup_path)
            return

        log_info(
            f"[UPDATE] Pengunduhan & verifikasi SHA-256 berhasil"
            f" ({calculated_sha256[:10]}...). Menjalankan installer..."
        )

        # 4. Delegasikan Eksekusi ke Batch Script (.bat) untuk menghindari Deadlock
        bat_path = os.path.join(temp_dir, "run_update.bat")
        
        with open(bat_path, "w") as bat_file:
            bat_file.write("@echo off\n")
            
            # Beri jeda 3 detik agar WatchersAgent (Python) punya waktu untuk mati 100% 
            # dan Windows melepas file lock sebelum uninstaller bekerja.
            bat_file.write("timeout /t 3 /nobreak >nul\n") 

            # Tanpa menjalankan Uninstaller memang bisa tapi client akan ada jeda 
            # sekitar 5-10 detik sebelum installer baru bisa menimpa file lama. 
            # Sehingga lebih baik menjalankan Uninstaller terlebih dahulu jika ada.
            if os.path.exists(app_dir) and os.path.exists(uninstaller_path):
                            # Uninstaller berjalan baris per baris (sinkronus) di CMD
                            bat_file.write(f'"{uninstaller_path}" /VERYSILENT /SUPPRESSMSGBOXES "_?={app_dir}"\n')
                        
            
            # Jalankan Installer Baru
            bat_file.write(f'"{setup_path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="{log_path}"\n')

            # Hapus file installer (.exe) setelah instalasi selesai tuntas
            bat_file.write(f'if exist "{setup_path}" del /f /q "{setup_path}"\n')

            # Perintah ini akan menghapus file run_update.bat ini sendiri setelah selesai
            bat_file.write('(goto) 2>nul & del "%~f0"\n')

        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000

        # Jalankan file bat secara lepas (detached)
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True
        )

        log_info(f"[END] Batch script untuk silent update telah dijalankan: {bat_path}")
        log_info (f"[END] Installer baru akan dijalankan secara silent. Log update akan disimpan di: {log_path}")
        log_info(f"[END] Script instalasi dipicu. Mematikan Agent seketika untuk mencegah Deadlock.")

        # WAJIB: Hentikan aplikasi Agent ini secara paksa (Seketika)
        # File lock akan terlepas, uninstaller bebas bekerja, dan aplikasi tidak akan membalas socket lagi.
        os._exit(0)

    except Exception as e:
        log_error(f"[UPDATE ERROR] Gagal mengeksekusi silent update: {e}")
        if os.path.exists(setup_path):
            try:
                os.remove(setup_path)
            except Exception:
                pass
    finally:
        with download_lock:
            is_downloading = False
            download_percentage = 0.0