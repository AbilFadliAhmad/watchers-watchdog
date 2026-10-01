import ctypes
import logging
import os
import traceback

LOG_DIR = os.path.join(
    os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "WatchersAgent"
)
LOG_FILE = os.path.join(LOG_DIR, "service_debug.log")

try:
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception:
    pass


def get_current_session_id() -> int:
    """Mengambil Session ID Windows dari proses saat ini."""
    try:
        session_id = ctypes.c_ulong()
        ctypes.windll.kernel32.ProcessIdToSessionId(
            os.getpid(), ctypes.byref(session_id)
        )
        return session_id.value
    except Exception:
        return -1


# Handler khusus agar setiap log langsung di-flush ke disk (Anti 0-Byte Log)
class AutoFlushFileHandler(logging.FileHandler):

    def emit(self, record):
        super().emit(record)
        self.flush()


class SessionFormatter(logging.Formatter):

    def format(self, record):
        record.session_id = get_current_session_id()
        return super().format(record)


# Konfigurasi Logger
logger = logging.getLogger("WatchersLogger")
logger.setLevel(logging.DEBUG)

file_handler = AutoFlushFileHandler(LOG_FILE, encoding="utf-8")
formatter = SessionFormatter(
    fmt="%(asctime)s [%(levelname)s] [Session:%(session_id)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


def log_info(message: str):
    logger.info(message)


def log_error(message: str, exc: Exception = None):
    if exc:
        full_err = f"{message} | Exception: {exc}\n{traceback.format_exc()}"
        logger.error(full_err)
    else:
        logger.error(message)


# CATAT LOG PERTAMA KALI SAAT MODUL DIBUKA (Memastikan log tidak 0-Byte)
log_info(
    f"=== WATCHERS AGENT INITIALIZED | PID: {os.getpid()} | SESSION: {get_current_session_id()} ==="
)