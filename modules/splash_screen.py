"""
Splash Screen con video de introducción — AspectFill, fullscreen, máx 5 segundos
"""
import tkinter as tk
import cv2
from PIL import Image, ImageTk
import os

MAX_SECONDS = 5   # duración máxima del splash


class SplashScreen(tk.Toplevel):
    def __init__(self, parent, video_path, callback, screen_w=None, screen_h=None):
        super().__init__(parent)

        self.callback   = callback
        self.video_path = video_path

        # Fullscreen real — usa ctypes para evitar problemas de DPI scaling en Windows
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            self.screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            self.screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        except Exception:
            self.screen_w = screen_w or self.winfo_screenwidth()
            self.screen_h = screen_h or self.winfo_screenheight()

        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.configure(bg="#000000")
        self.geometry(f"{self.screen_w}x{self.screen_h}+0+0")
        self.update_idletasks()
        self.lift()
        self.focus_force()

        self.video_label = tk.Label(self, bg="#000000", bd=0)
        self.video_label.pack(fill="both", expand=True)

        self.video_activo  = True
        self.cap           = None
        self.en_fade_out   = False
        self._last_pil     = None
        self._frame_count  = 0

        # Delay mayor para que Windows procese la geometría antes del video
        self.after(200, self.iniciar_video)

    # ------------------------------------------------------------------
    def iniciar_video(self):
        if not os.path.exists(self.video_path):
            self.cerrar()
            return

        try:
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                self.cerrar()
                return

            self.fps        = self.cap.get(cv2.CAP_PROP_FPS) or 30
            self.delay      = max(1, int(1000 / self.fps))
            self.max_frames = int(self.fps * MAX_SECONDS)
            self.reproducir_frame()

        except Exception as e:
            print(f"[SPLASH] Error: {e}")
            self.cerrar()

    # ------------------------------------------------------------------
    def _aspect_fill(self, frame):
        """Escala el frame para cubrir toda la pantalla (recorte centrado)."""
        fh, fw = frame.shape[:2]
        sw, sh = self.screen_w, self.screen_h

        scale = max(sw / fw, sh / fh)
        nw    = int(fw * scale)
        nh    = int(fh * scale)

        frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)

        x0 = (nw - sw) // 2
        y0 = (nh - sh) // 2
        return frame[y0:y0 + sh, x0:x0 + sw]

    # ------------------------------------------------------------------
    def reproducir_frame(self):
        if not self.video_activo or not self.cap:
            return

        try:
            # Límite de 5 segundos
            if self._frame_count >= self.max_frames:
                if not self.en_fade_out:
                    self.en_fade_out = True
                    self.iniciar_fade_out()
                return

            ret, frame = self.cap.read()

            if not ret:
                if not self.en_fade_out:
                    self.en_fade_out = True
                    self.iniciar_fade_out()
                return

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = self._aspect_fill(frame)

            img            = Image.fromarray(frame)
            self._last_pil = img
            photo          = ImageTk.PhotoImage(img)
            self.video_label.config(image=photo)
            self.video_label.image = photo

            self._frame_count += 1
            self.after(self.delay, self.reproducir_frame)

        except Exception as e:
            print(f"[SPLASH] Error frame: {e}")
            self.cerrar()

    # ------------------------------------------------------------------
    def iniciar_fade_out(self):
        self.fade_steps = 20
        self.fade_step  = 0
        self.animar_fade_out()

    def animar_fade_out(self):
        if self.fade_step <= self.fade_steps:
            alpha = 1.0 - (self.fade_step / self.fade_steps)
            sw, sh = self.screen_w, self.screen_h
            negro  = Image.new("RGB", (sw, sh), (0, 0, 0))
            try:
                blended = Image.blend(self._last_pil, negro, 1.0 - alpha)
                photo   = ImageTk.PhotoImage(blended)
            except Exception:
                photo = ImageTk.PhotoImage(negro)
            self.video_label.config(image=photo)
            self.video_label.image = photo
            self.fade_step += 1
            self.after(20, self.animar_fade_out)
        else:
            self.after(100, self.cerrar)

    # ------------------------------------------------------------------
    def cerrar(self):
        self.video_activo = False
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass
        if self.callback:
            self.callback()
