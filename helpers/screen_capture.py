import os
import time
import threading
import ctypes
import numpy as np
from PIL import Image
from typing import Optional, Tuple
from config import SCREENSHOTS_DIR, SCREENSHOT_INTERVAL, SLIDE_CHANGE_THRESHOLD, MONITOR_INDEX
from helpers.database import save_screenshot_record
from helpers.utils.formatters import format_seconds_to_timestamp


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', ctypes.c_uint32),
        ('biWidth', ctypes.c_int32),
        ('biHeight', ctypes.c_int32),
        ('biPlanes', ctypes.c_uint16),
        ('biBitCount', ctypes.c_uint16),
        ('biCompression', ctypes.c_uint32),
        ('biSizeImage', ctypes.c_uint32),
        ('biXPelsPerMeter', ctypes.c_int32),
        ('biYPelsPerMeter', ctypes.c_int32),
        ('biClrUsed', ctypes.c_uint32),
        ('biClrImportant', ctypes.c_uint32),
    ]


def capture_screen_gdi(monitor_index: int = 0) -> Optional[Image.Image]:
    """Captura o monitor primário ou secundário usando GDI BitBlt nativo do Windows."""
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        # Resolução e coordenadas
        # Monitor 0 (Primário): 0, 0, 1920, 1080 (ou SM_CXSCREEN, SM_CYSCREEN)
        # Monitor 1 (Secundário se existir): 1920, 0, 1920, 1080
        width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        height = user32.GetSystemMetrics(1) # SM_CYSCREEN

        left = 0
        top = 0
        if monitor_index == 1:
            left = width  # Deslocamento para o segundo monitor

        hdc = user32.GetDC(0)
        memdc = gdi32.CreateCompatibleDC(hdc)
        hbmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
        gdi32.SelectObject(memdc, hbmp)

        SRCCOPY = 0x00CC0020
        gdi32.BitBlt(memdc, 0, 0, width, height, hdc, left, top, SRCCOPY)

        header = BITMAPINFOHEADER(
            ctypes.sizeof(BITMAPINFOHEADER),
            width,
            -height,  # Negativo para orientação top-down
            1,
            32,
            0,
            0,
            0,
            0,
            0,
            0
        )
        buf = (ctypes.c_char * (width * height * 4))()
        gdi32.GetDIBits(memdc, hbmp, 0, height, buf, ctypes.byref(header), 0)

        arr = np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 4))
        # Converte de BGRA para RGB
        rgb_img = Image.fromarray(arr[:, :, [2, 1, 0]])

        # Limpa objetos GDI para não vazar memória
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(0, hdc)

        return rgb_img
    except Exception as e:
        print(f"[ScreenCapture] Erro ao capturar tela via GDI: {e}")
        return None


def calculate_image_diff(img1: Image.Image, img2: Image.Image) -> float:
    """Calcula a diferença percentual entre duas imagens redimensionadas para detectar mudança de slide."""
    try:
        # Reduz para 64x64 em escala de cinza para comparação rápida e robusta
        small1 = np.array(img1.convert("L").resize((64, 64)), dtype=np.float32)
        small2 = np.array(img2.convert("L").resize((64, 64)), dtype=np.float32)

        # Diferença absoluta média normalizada (0.0 a 1.0)
        diff = np.mean(np.abs(small1 - small2)) / 255.0
        return float(diff)
    except Exception:
        return 1.0


class ScreenCaptureManager:
    def __init__(self):
        self.is_capturing = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.active_lesson_id: Optional[int] = None
        self.start_time: float = 0.0
        self.last_image: Optional[Image.Image] = None
        self.last_screenshot_filename: Optional[str] = None
        self.captured_count: int = 0

    def start(self, lesson_id: int):
        with self._lock:
            if self.is_capturing:
                return
            self.is_capturing = True
            self.active_lesson_id = lesson_id
            self.start_time = time.time()
            self.last_image = None
            self.last_screenshot_filename = None
            self.captured_count = 0
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()

    def _save_slide(self, img: Image.Image, elapsed: float, is_manual: int = 0) -> str:
        timestamp_str = format_seconds_to_timestamp(elapsed)
        timestamp_slug = timestamp_str.replace(":", "-")
        filename = f"lesson_{self.active_lesson_id}_{timestamp_slug}_{int(time.time()) % 10000}.png"
        filepath = os.path.join(SCREENSHOTS_DIR, filename)

        # Otimiza o PNG para carregamento ágil
        img.save(filepath, format="PNG", optimize=True)

        if self.active_lesson_id:
            save_screenshot_record(
                lesson_id=self.active_lesson_id,
                timestamp_seconds=elapsed,
                timestamp_str=timestamp_str,
                filename=filename,
                is_manual=is_manual
            )

        self.last_image = img
        self.last_screenshot_filename = filename
        self.captured_count += 1
        return filename

    def capture_now(self) -> Optional[str]:
        """Tira um print manual imediatamente."""
        if not self.is_capturing or not self.active_lesson_id:
            return None

        elapsed = max(0.0, time.time() - self.start_time)
        img = capture_screen_gdi(MONITOR_INDEX)
        if img:
            return self._save_slide(img, elapsed, is_manual=1)
        return None

    def _capture_loop(self):
        # Tira o primeiro print imediatamente (slide inicial da aula)
        initial_img = capture_screen_gdi(MONITOR_INDEX)
        if initial_img:
            self._save_slide(initial_img, 0.0, is_manual=0)

        while self.is_capturing:
            time.sleep(SCREENSHOT_INTERVAL)
            if not self.is_capturing:
                break

            try:
                curr_img = capture_screen_gdi(MONITOR_INDEX)
                if curr_img is None:
                    continue

                elapsed = max(0.0, time.time() - self.start_time)

                # Se for a primeira imagem ou mudou em relação ao slide anterior
                if self.last_image is None:
                    self._save_slide(curr_img, elapsed)
                else:
                    diff = calculate_image_diff(self.last_image, curr_img)
                    if diff >= SLIDE_CHANGE_THRESHOLD:
                        print(f"[ScreenCapture] Novo slide detectado (diff={diff:.3f}) no segundo {elapsed:.1f}")
                        self._save_slide(curr_img, elapsed)

            except Exception as e:
                print(f"[ScreenCapture] Erro no loop de captura: {e}")

    def stop(self):
        with self._lock:
            self.is_capturing = False

        if self._thread:
            self._thread.join(timeout=2.0)


# Instância global singleton
screen_capture = ScreenCaptureManager()
