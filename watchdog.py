import subprocess
import time

TARGET_PROCESS = "WatchersAgent.exe"
TASK_NAME = "WatchersAgentTask"


def is_process_running(process_name):
    """Mengecek apakah proses target ada di Task Manager."""
    try:
        # Menjalankan tasklist tanpa memicu jendela konsol
        output = subprocess.check_output(
            f'tasklist /FI "IMAGENAME eq {process_name}"',
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        return process_name.lower() in output.lower()
    except Exception:
        return False


def main():
    while True:
        try:
            # Jika WatchersAgent.exe terdeteksi mati/di-kill
            if not is_process_running(TARGET_PROCESS):
                # Trigger Task Scheduler untuk membangkitkannya di Session 1
                subprocess.run(
                    f'schtasks /run /tn "{TASK_NAME}"',
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass

        # Jeda pemeriksaan setiap 2 detik
        time.sleep(2)


if __name__ == "__main__":
    main()