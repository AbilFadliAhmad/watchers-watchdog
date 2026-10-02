import subprocess
import time
from service_logger import log_error, log_info
import socket
import threading
from capture_image import capture_winlogon_desktop
from macro_typing import handle_key_injection

TARGET_PROCESS = "WatchersAgent.exe"
TASK_NAME = "WatchersAgentTask"

# Untuk menjalankan perintah shutdown maupun restart dari agent
def run_ipc_server():
    """Socket Server internal yang berjalan di background Service (SYSTEM)."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Reuse address agar port bisa langsung dipasang saat restart
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind(("127.0.0.1", 58888))
        server.listen(5)
        log_info("[IPC Server] Listening di 127.0.0.1:58888...")

        while True:
            conn, _ = server.accept()
            data = conn.recv(1024).decode("utf-8").strip()

            if data == "SHUTDOWN":
                log_info(
                    "[IPC Command] Menerima perintah SHUTDOWN dari Agent. Mematikan sistem..."
                )
                subprocess.run(
                    "shutdown /s /f /t 0",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    shell=True,
                )

            elif data == "RESTART":
                log_info(
                    "[IPC Command] Menerima perintah RESTART dari Agent. Merestart sistem..."
                )
                subprocess.run(
                    "shutdown /r /f /t 0",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    shell=True,
                )
            elif data == "GET_WINLOGON_FRAME":
                frame_bytes = capture_winlogon_desktop()  # Fungsi SetThreadDesktop Winlogon
                conn.sendall(frame_bytes)
            elif data.startswith("INJECT_KEY:"):
                # Format data: "INJECT_KEY:Key.enter:press" atau "INJECT_KEY:a:press"
                parts = data.split(":")
                if len(parts) >= 3:
                    key_str = parts[1]
                    action = parts[2]
                    handle_key_injection(key_str, action)

            conn.close()
    except Exception as e:
        log_error(f"[IPC Server] Error pada server socket: {e}")

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
            capture_output=True,
            text=True,
        )
    except Exception as e:
        log_error(f"Error kill_process_by_pid: {e}")

def trigger_agent_task():
    """Memicu Task Scheduler untuk menjalankan WatchersAgent.exe secara instan."""
    try:
        # 1. Paksa reset status task jika masih dianggap 'Running' oleh Task Scheduler
        subprocess.run(
            f'schtasks /end /tn "{TASK_NAME}"',
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)

        # 2. Jalankan ulang task
        result = subprocess.run(
            f'schtasks /run /tn "{TASK_NAME}"',
            creationflags=subprocess.CREATE_NO_WINDOW,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            err_msg = result.stderr.strip() or result.stdout.strip()
            log_error(f"Gagal memicu task '{TASK_NAME}': {err_msg}")
        else:
            log_info(
                f"[✓] Berhasil memicu task '{TASK_NAME}' via Task Scheduler."
            )

    except Exception as e:
        log_error(f"Exception saat memicu {TASK_NAME}: {e}")

def main():
    # 1. Jalankan IPC Server di Thread terpisah
    ipc_thread = threading.Thread(target=run_ipc_server, daemon=True)
    ipc_thread.start()

    # 2. Loop Utama Watchdog (Hanya memastikan WatchersAgent.exe selalu hidup)
    while True:
        try:
            processes = get_all_agent_processes(TARGET_PROCESS)
            has_session_1_or_higher = False

            for pid, session_id in processes:
                if session_id == 0:
                    # Jika ada instance yang tersasar di Session 0, kill PID tersebut
                    kill_process_by_pid(pid)
                elif session_id > 0:
                    has_session_1_or_higher = True

            # Jalankan Agent HANYA jika TIDAK ADA instance yang aktif di Session 1/User
            if not has_session_1_or_higher:
                trigger_agent_task()

        except Exception as e:
            log_error(f"Error pada Watchdog loop: {e}")

        # Pengecekan rutin setiap 2 detik
        time.sleep(2)


if __name__ == "__main__":
    main()