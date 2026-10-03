import ctypes
from ctypes import wintypes
import io

# --- Win32 API DLLs ---
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# --- Win32 API Constants ---
WINSTA_ALL_ACCESS = 0x37F
DESKTOP_ALL_ACCESS = (
    0x0100 | 0x0001 | 0x0002 | 0x0008 | 0x0010 | 0x0020 | 0x0040 | 0x0080
)
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


def capture_winlogon_desktop() -> bytes:
    """Mengambil screenshot layar Winlogon / Lock Screen dari Session 0 (SYSTEM).

    Menghubungkan proses ke WinSta0 dan mengidentifikasi Input Desktop aktif.
    """
    h_orig_winsta = user32.GetProcessWindowStation()
    current_thread_id = kernel32.GetCurrentThreadId()
    h_orig_desktop = user32.GetThreadDesktop(current_thread_id)

    h_winsta = None
    h_desktop = None

    try:
        # 1. Buka dan BIND ke WindowStation "WinSta0" (WindowStation Interaktif User)
        h_winsta = user32.OpenWindowStationW("WinSta0", False, WINSTA_ALL_ACCESS)
        if not h_winsta or not user32.SetProcessWindowStation(h_winsta):
            return b""

        # 2. Buka Desktop yang sedang MENGUASAI INPUT LAYAR (Winlogon / Lock Screen)
        h_desktop = user32.OpenInputDesktop(0, False, DESKTOP_ALL_ACCESS)
        if not h_desktop or not user32.SetThreadDesktop(h_desktop):
            return b""

        # 3. Dapatkan resolusi layar aktif
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        if width <= 0 or height <= 0:
            return b""

        # 4. Capture Framebuffer GDI
        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        h_bitmap = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
        h_old_bitmap = gdi32.SelectObject(hdc_mem, h_bitmap)

        # Copy data dari layar ke Memory DC
        gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, 0, 0, SRCCOPY)

        # Extract Raw BGRX Data
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height  # Top-Down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0

        image_data_size = width * height * 4
        buffer = ctypes.create_string_buffer(image_data_size)
        gdi32.GetDIBits(
            hdc_mem,
            h_bitmap,
            0,
            height,
            buffer,
            ctypes.byref(bmi),
            DIB_RGB_COLORS,
        )

        # Cleanup Handles GDI
        gdi32.SelectObject(hdc_mem, h_old_bitmap)
        gdi32.DeleteObject(h_bitmap)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        # 5. Build Native BMP Header (54 bytes)
        bmp_header_size = 54
        file_size = bmp_header_size + image_data_size

        bmp_stream = io.BytesIO()

        # File Header (14 bytes)
        bmp_stream.write(b"BM")
        bmp_stream.write(file_size.to_bytes(4, "little"))
        bmp_stream.write(b"\x00\x00\x00\x00")
        bmp_stream.write(bmp_header_size.to_bytes(4, "little"))

        # DIB Header (40 bytes)
        bmp_stream.write(bmi.bmiHeader.biSize.to_bytes(4, "little"))
        bmp_stream.write(bmi.bmiHeader.biWidth.to_bytes(4, "little"))
        bmp_stream.write(
            bmi.bmiHeader.biHeight.to_bytes(4, "little", signed=True)
        )
        bmp_stream.write(bmi.bmiHeader.biPlanes.to_bytes(2, "little"))
        bmp_stream.write(bmi.bmiHeader.biBitCount.to_bytes(2, "little"))
        bmp_stream.write(bmi.bmiHeader.biCompression.to_bytes(4, "little"))
        bmp_stream.write(image_data_size.to_bytes(4, "little"))
        bmp_stream.write(b"\x00\x00\x00\x00")
        bmp_stream.write(b"\x00\x00\x00\x00")
        bmp_stream.write(b"\x00\x00\x00\x00")
        bmp_stream.write(b"\x00\x00\x00\x00")

        # Pixel Bytes
        bmp_stream.write(buffer.raw)

        return bmp_stream.getvalue()

    except Exception as e:
        log_error(F"Screenshoot salah: {e}")
        return b""

    finally:
        # Restore Thread Desktop & Process WindowStation
        if h_orig_desktop:
            user32.SetThreadDesktop(h_orig_desktop)
        if h_desktop:
            user32.CloseDesktop(h_desktop)
        if h_orig_winsta:
            user32.SetProcessWindowStation(h_orig_winsta)
        if h_winsta:
            user32.CloseWindowStation(h_winsta)