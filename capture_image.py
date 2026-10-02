import ctypes
from ctypes import wintypes
import io

# --- Win32 API Constants & Structs ---
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
    """Mengambil screenshot layar Winlogon (Lock Screen / Login Screen).

    Khusus dipanggil oleh WatchersService (Session 0 / NT AUTHORITY\\SYSTEM).
    Mengembalikan data gambar native asli dalam format BMP (bytes) tanpa library Pillow.
    """
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    # Simpan handle desktop thread asal untuk dikembalikan setelah selesai
    h_orig_desktop = user32.GetThreadDesktop(user32.GetCurrentThreadId())

    # 1. Buka Desktop Winlogon
    h_winlogon_desktop = user32.OpenDesktopW(
        "Winlogon", 0, False, DESKTOP_ALL_ACCESS
    )
    if not h_winlogon_desktop:
        return b""

    try:
        # 2. Pindahkan Thread Service ke Desktop Winlogon
        if not user32.SetThreadDesktop(h_winlogon_desktop):
            return b""

        # 3. Dapatkan resolusi layar Winlogon
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        if width <= 0 or height <= 0:
            return b""

        # 4. Inisialisasi GDI Device Context
        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        h_bitmap = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
        h_old_bitmap = gdi32.SelectObject(hdc_mem, h_bitmap)

        # 5. Salin frame buffer Winlogon ke Memory DC
        gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, 0, 0, SRCCOPY)

        # 6. Ekstrak data piksel raw (BGRX)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height  # Nilai negatif agar orientasi Top-Down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB

        # Ukuran data pixel BGRX adalah width * height * 4 byte
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

        # 7. Pembersihan Handle GDI
        gdi32.SelectObject(hdc_mem, h_old_bitmap)
        gdi32.DeleteObject(h_bitmap)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        # 8. Membuat Header File BMP Native (Tanpa Library Eksternal)
        # BMP Header (14 bytes) + DIB Header (40 bytes) = 54 bytes
        bmp_header_size = 54
        file_size = bmp_header_size + image_data_size

        bmp_stream = io.BytesIO()

        # File Header (14 bytes)
        bmp_stream.write(b'BM')  # Signature
        bmp_stream.write(file_size.to_bytes(4, 'little'))  # Total ukuran file
        bmp_stream.write(b'\x00\x00\x00\x00')  # Reserved
        bmp_stream.write(bmp_header_size.to_bytes(4, 'little'))  # Offset data piksel

        # DIB Header / BITMAPINFOHEADER (40 bytes)
        bmp_stream.write(bmi.bmiHeader.biSize.to_bytes(4, 'little'))
        bmp_stream.write(bmi.bmiHeader.biWidth.to_bytes(4, 'little'))
        bmp_stream.write(bmi.bmiHeader.biHeight.to_bytes(4, 'little', signed=True))
        bmp_stream.write(bmi.bmiHeader.biPlanes.to_bytes(2, 'little'))
        bmp_stream.write(bmi.bmiHeader.biBitCount.to_bytes(2, 'little'))
        bmp_stream.write(bmi.bmiHeader.biCompression.to_bytes(4, 'little'))
        bmp_stream.write(image_data_size.to_bytes(4, 'little'))  # Ukuran data mentah
        bmp_stream.write(b'\x00\x00\x00\x00')  # X pixels per meter
        bmp_stream.write(b'\x00\x00\x00\x00')  # Y pixels per meter
        bmp_stream.write(b'\x00\x00\x00\x00')  # Total warna (0 = default)
        bmp_stream.write(b'\x00\x00\x00\x00')  # Warna penting (0)

        # Tulis data pixel asli langsung dari buffer Windows ke dalam stream
        bmp_stream.write(buffer.raw)

        return bmp_stream.getvalue()

    except Exception:
        return b""

    finally:
        # 9. Kembalikan Thread ke Desktop Asal & Tutup Handle Desktop
        if h_orig_desktop:
            user32.SetThreadDesktop(h_orig_desktop)
        if h_winlogon_desktop:
            user32.CloseDesktop(h_winlogon_desktop)