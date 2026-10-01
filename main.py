import subprocess
import time
from service_logger import log_error

TARGET_PROCESS = "WatchersAgent.exe"
TASK_NAME = "WatchersAgentTask"


def is_user_logged_in():
    """Mengecek apakah pengguna sudah masuk ke desktop (explorer.exe aktif)."""
    try:
        output = subprocess.check_output(
            'tasklist /FI "IMAGENAME eq explorer.exe"',
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        return "explorer.exe" in output.lower()
    except Exception as e:
        log_error(f"Error Logged IN: {e}")
        return False


def get_all_agent_processes(process_name):
    """Mendapatkan daftar tuple (PID, Session_ID) untuk SEMUA instance proses yang berjalan."""
    processes = []
    try:
        output = subprocess.check_output(
            f'tasklist /FI "IMAGENAME eq {process_name}" /FO CSV /NH',
            creationflags=subprocess.CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")

        lines = output.strip().split("\n")
        for line in lines:
            if process_name.lower() in line.lower():
                parts = line.split('","')
                if len(parts) >= 4:
                    pid_str = parts[1].replace('"', "").strip()
                    session_str = parts[3].replace('"', "").strip()
                    if pid_str.isdigit() and session_str.isdigit():
                        processes.append((int(pid_str), int(session_str)))
    except Exception as e:
        log_error(f"Error get_all_agent_processes: {e}")
        pass
    return processes


def kill_process_by_pid(pid):
    """Mematikan proses spesifik secara paksa berdasarkan PID."""
    try:
        subprocess.run(
            f"taskkill /F /PID {pid}",
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        log_error(f"Error kill_process_by_pid: {e}")
        pass


def trigger_agent_task():
    """Memicu Task Scheduler untuk menjalankan WatchersAgent.exe."""
    try:
        subprocess.run(
            f'schtasks /run /tn "{TASK_NAME}"',
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        log_error(f"Gagal memicu {TASK_NAME}: {e}")


def main():
    last_logged_in_state = None

    while True:
        try:
            user_logged_in = is_user_logged_in()
            processes = get_all_agent_processes(TARGET_PROCESS)

            # 1. Jika terjadi transisi (misal: dari Halaman Login masuk ke Desktop / sebaliknya)
            if (
                last_logged_in_state is not None
                and last_logged_in_state != user_logged_in
            ):
                # Kill seluruh PID agar di-attach ulang ke desktop session yang baru
                for pid, _ in processes:
                    kill_process_by_pid(pid)
                time.sleep(1)
                processes = []

            last_logged_in_state = user_logged_in

            # 2. Periksa status session setiap PID
            has_session_1_or_higher = False

            for pid, session_id in processes:
                if session_id == 0:
                    # Jika ada instance yang terjebak di Session 0, kill PID tersebut!
                    kill_process_by_pid(pid)
                elif session_id > 0:
                    has_session_1_or_higher = True

            # 3. Jalankan Task Scheduler HANYA jika TIDAK ADA instance di Session 1 (User Session)
            if not has_session_1_or_higher:
                trigger_agent_task()

        except Exception as e:
            log_error(f"Error pada Watchdog loop: {e}")
            print(f"Error pada Watchdog loop: {e}")

        print('terkenal')
        # Pengecekan rutin setiap 3 detik
        time.sleep(3)


if __name__ == "__main__":
    main()