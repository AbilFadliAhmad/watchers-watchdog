import ctypes
from ctypes import wintypes
from service_logger import log_error

# --- CONSTANTS & STRUCTS WIN32 API ---
DESKTOP_ALL_ACCESS = (
    0x0100 | 0x0001 | 0x0002 | 0x0008 | 0x0010 | 0x0020 | 0x0040 | 0x0080
)
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

# --- TABEL VIRTUAL KEY (VK) CODES WINDOWS ---
VK_MAPPING = {
    "Key.enter": 0x0D,  # Enter
    "Key.backspace": 0x08,  # Backspace
    "Key.tab": 0x09,  # Tab
    "Key.space": 0x20,  # Spasi
    "Key.esc": 0x1B,  # Escape
    "Key.shift": 0x10,  # Shift
    "Key.ctrl": 0x11,  # Control
    "Key.alt": 0x12,  # Alt
    "Key.delete": 0x2E,  # Delete
    "Key.up": 0x26,  # Panah Atas
    "Key.down": 0x28,  # Panah Bawah
    "Key.left": 0x25,  # Panah Kiri
    "Key.right": 0x27,  # Panah Kanan
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


# --- ATTACH / DETACH DESKTOP AKTIF ---
def attach_to_active_desktop():
    """Attach thread saat ini ke desktop yang sedang aktif menerima input (Winlogon atau Default)."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel3
    current_thread_id = kernel32.GetCurrentThreadId()
    h_orig = user32.GetThreadDesktop(current_thread_id)
    h_active = user32.OpenInputDesktop(0, False, DESKTOP_ALL_ACCESS)

    if h_active:
        user32.SetThreadDesktop(h_active)
        return h_orig, h_active
    return h_orig, None


def detach_desktop(h_orig, h_active):
    """Mengembalikan thread ke desktop awal dan melepas handle desktop aktif."""
    user32 = ctypes.windll.user32
    if h_orig:
        user32.SetThreadDesktop(h_orig)
    if h_active:
        user32.CloseDesktop(h_active)


# --- FUNGSI INJEKSI WIN32 ---
def inject_unicode_char(char: str, is_keyup: bool = False):
    """Injeksi karakter biasa (a-z, A-Z, 0-9, simbol) via Unicode Scan Code."""
    h_orig, h_active = attach_to_active_desktop()
    if not h_active:
        return

    try:
        extra = ctypes.c_ulong(0)
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = 0
        inp.union.ki.wScan = ord(char)

        flags = KEYEVENTF_UNICODE
        if is_keyup:
            flags |= KEYEVENTF_KEYUP

        inp.union.ki.dwFlags = flags
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = ctypes.pointer(extra)

        ctypes.windll.user32.SendInput(
            1, ctypes.byref(inp), ctypes.sizeof(INPUT)
        )
    except Exception as e:
        log_error(f"Error inject_unicode_char: {e}")
    finally:
        detach_desktop(h_orig, h_active)


def inject_virtual_key(vk_code: int, is_keyup: bool = False):
    """Injeksi tombol kontrol/spesial (Enter, Backspace, Tab, dll) via Virtual Key Code."""
    h_orig, h_active = attach_to_active_desktop()
    if not h_active:
        return

    try:
        extra = ctypes.c_ulong(0)
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk_code
        inp.union.ki.wScan = 0
        inp.union.ki.dwFlags = KEYEVENTF_KEYUP if is_keyup else 0
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = ctypes.pointer(extra)

        ctypes.windll.user32.SendInput(
            1, ctypes.byref(inp), ctypes.sizeof(INPUT)
        )
    except Exception as e:
        log_error(f"Error inject_virtual_key: {e}")
    finally:
        detach_desktop(h_orig, h_active)


def handle_key_injection(key_str: str, action: str):
    """Handler tunggal untuk memilah apakah tombol spesial atau karakter unicode."""
    is_keyup = action == "release"

    # 1. Jika tombol termasuk dalam daftar tombol spesial (Enter, Backspace, Tab, dll)
    if key_str in VK_MAPPING:
        inject_virtual_key(VK_MAPPING[key_str], is_keyup=is_keyup)

    # 2. Jika tombol merupakan karakter tunggal biasa (huruf, angka, simbol)
    elif len(key_str) == 1:
        inject_unicode_char(key_str, is_keyup=is_keyup)