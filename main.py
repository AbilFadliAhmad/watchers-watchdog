import ctypes
from ctypes import wintypes
import socket
import subprocess
import threading
import time
from capture_image import capture_winlogon_desktop
from service_logger import log_error, log_info

TARGET_PROCESS = "WatchersAgent.exe"
TASK_NAME = "WatchersAgentTask"

# --- WIN32 API CONSTANTS & STRUCTS ---
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_TERMINATE = 0x0001

kernel32 = ctypes.windll.kernel32


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def get_all_agent_processes_fast(process_name: str):
    """Mendapatkan daftar (PID, Session_ID) secara native dari RAM (< 1 ms) tanpa tasklist.exe."""
    processes = []
    h_snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if h_snapshot == -1 or h_snapshot == 0xFFFFFFFF:
        return processes

    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    target_lower = process_name.lower()

    if kernel32.Process32FirstW(h_snapshot, ctypes.byref(entry)):
        while True:
            if entry.szExeFile.lower() == target_lower:
                pid = entry.th32ProcessID
                session_id = wintypes.DWORD()
                if kernel32.ProcessIdToSessionId(
                    pid, ctypes.byref(session_id)
                ):
                    processes.append((pid, session_id.value))

            if not kernel32.Process32NextW(h_snapshot, ctypes.byref(entry)):
                break

    kernel32.CloseHandle(h_snapshot)
    return processes


def kill_process_by_pid_fast(pid: int):
    """Mematikan proses tersasar di Session 0 secara instan via Win32 API tanpa taskkill."""
    h_proc = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if h_proc:
        kernel32.TerminateProcess(h_proc, 1)
        kernel32.CloseHandle(h_proc)


def trigger_agent_task_fast():
    """Memicu Task Scheduler secara instan tanpa delay time.sleep."""
    try:
        # Panggil schtasks /run secara langsung
        result = subprocess.run(
            f'schtasks /run /tn "{TASK_NAME}"',
            creationflags=subprocess.CREATE_NO_WINDOW,
            capture_output=True,
            text=True,
        )

        # Jika task tersangkut dalam status 'Running', paksa reset dan jalankan kembali
        if result.returncode != 0:
            subprocess.run(
                f'schtasks /end /tn "{TASK_NAME}"',
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            subprocess.run(
                f'schtasks /run /tn "{TASK_NAME}"',
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            log_info(
                f"[✓] Berhasil mereset & memicu task '{TASK_NAME}' via Task"
                " Scheduler."
            )
        else:
            log_info(
                f"[✓] Berhasil memicu task '{TASK_NAME}' via Task Scheduler."
            )

    except Exception as e:
        log_error(f"Exception saat memicu {TASK_NAME}: {e}")


def run_ipc_server():
    """Socket Server internal yang berjalan di background Service (SYSTEM)."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind(("127.0.0.1", 58888))
        server.listen(5)
        log_info("[IPC Server] Listening di 127.0.0.1:58888...")

        while True:
            conn, _ = server.accept()
            data = conn.recv(1024).decode("utf-8").strip()
            log_info(f"Perintah Terkirim: {data}")

            if data == "SHUTDOWN":
                log_info(
                    "[IPC Command] Menerima perintah SHUTDOWN dari Agent."
                    " Mematikan sistem..."
                )
                subprocess.run(
                    "shutdown /s /f /t 0",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    shell=True,
                )

            elif data == "RESTART":
                log_info(
                    "[IPC Command] Menerima perintah RESTART dari Agent."
                    " Merestart sistem..."
                )
                subprocess.run(
                    "shutdown /r /f /t 0",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    shell=True,
                )
            elif data == "GET_WINLOGON_FRAME":
                frame_bytes = capture_winlogon_desktop()
                conn.sendall(frame_bytes)

            conn.close()
    except Exception as e:
        log_error(f"[IPC Server] Error pada server socket: {e}")


def main():
    ipc_thread = threading.Thread(target=run_ipc_server, daemon=True)
    ipc_thread.start()

    while True:
        try:
            # Penelusuran snapshot memori C++ (< 1 ms)
            processes = get_all_agent_processes_fast(TARGET_PROCESS)
            has_session_1_or_higher = False

            for pid, session_id in processes:
                if session_id == 0:
                    kill_process_by_pid_fast(pid)
                elif session_id > 0:
                    has_session_1_or_higher = True

            if not has_session_1_or_higher:
                trigger_agent_task_fast()

        except Exception as e:
            log_error(f"Error pada Watchdog loop: {e}")

        # Polling dipercepat ke 0.5 detik (Penggunaan CPU tetap < 0.1%)
        time.sleep(2)


if __name__ == "__main__":
    main()