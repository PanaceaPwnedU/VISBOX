# enroll_client.py
import sys
import sqlite3
import cv2
import face_recognition
import numpy as np
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

import core
from config import *
# СТРОГИЙ ИМПОРТ: забираем сканер из соседнего файла, чтобы не дублировать код камеры
from scanner import FaceScannerWidget

class EnrollClientWidget(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG_COLOR)
        core.init_db()
        
        # Внутреннее состояние процесса регистрации
        self.is_enrolling = False
        self.enroll_name = ""
        self.enroll_stage_idx = 0
        self.enroll_encodings = []
        self.flash_counter = 0
        
        # ШАГ 1: Встраиваем сканер как подчиненный компонент (видеоподложку)
        self.scanner = FaceScannerWidget(self)
        self.scanner.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # ШАГ 2: Информационное табло для оператора кадров
        self.status_label = tk.Label(self, text="PRESS CTRL+N TO START REGISTRATION", bg=BG_COLOR, fg=TEXT_MAIN, font=FONT_SANS_BOLD)
        self.status_label.pack(pady=10, fill=tk.X)
        
        # Горячие клавиши (привязаны ко всему приложению для перехвата фокуса)
        self.bind_all("<space>", lambda e: self.capture_stage_frame())
        self.bind_all("<Control-n>", lambda e: self.start_enrollment_dialog())
        
        # Запускаем локальный цикл проверки вспышки кадра
        self.update_flash_effect()

    def start_enrollment_dialog(self):
        """Открывает модальное окно ввода имени с жесткой фиксацией фокуса системы"""
        if self.is_enrolling: return
        
        dialog = tk.Toplevel(self)
        dialog.overrideredirect(True) # Убираем рамки ОС, чтобы Hyprland не ломал геометрию
        
        w, h = 400, 160
        dialog.geometry(f"{w}x{h}+{int(self.winfo_x()+self.winfo_width()/2-w/2)}+{int(self.winfo_y()+self.winfo_height()/2-h/2)}")
        dialog.configure(bg=TEXT_MUTED)
        
        inner = tk.Frame(dialog, bg=BG_COLOR)
        inner.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        tk.Label(inner, text="ENTER NEW EMPLOYEE NAME:", bg=BG_COLOR, fg=TEXT_MAIN, font=FONT_SANS).pack(pady=(15,5))
        
        entry = tk.Entry(inner, bg=SURFACE_COLOR, fg=TEXT_MAIN, insertbackground=TEXT_MAIN, font=FONT_SANS_BOLD, bd=0, justify='center')
        entry.pack(pady=5, fill=tk.X, padx=40, ipady=6)
        entry.focus()
        
        btn_frame = tk.Frame(inner, bg=BG_COLOR)
        btn_frame.pack(pady=10)
        
        def cancel_enroll():
            self.is_enrolling = False
            self.enroll_encodings = []
            self.status_label.config(text="REGISTRATION CANCELLED", fg=TEXT_MUTED)
            dialog.destroy()
            self.focus_force()

        def proceed():
            name = entry.get().strip()
            if name:
                self.is_enrolling = True
                self.enroll_name = name
                self.enroll_stage_idx = 0
                self.enroll_encodings = []
                self.status_label.config(text=f"[{name}] TURN STRAIGHT | PRESS SPACE", fg=ACCENT)
                dialog.destroy()
                self.focus_force()
            else: 
                messagebox.showerror("Error", "Name cannot be empty")
            
        tk.Button(btn_frame, text="CONFIRM", command=proceed, bg=SURFACE_COLOR, fg=TEXT_MAIN, bd=0, padx=15, pady=5).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="CANCEL", command=cancel_enroll, bg=SURFACE_COLOR, fg=TEXT_MUTED, bd=0, padx=15, pady=5).pack(side=tk.LEFT, padx=5)
        
        dialog.bind('<Return>', lambda e: proceed())
        dialog.bind('<Escape>', lambda e: cancel_enroll())
        
        dialog.grab_set() # Перехватываем глобальный фокус ввода

    def capture_stage_frame(self):
        """Забирает данные из кэша импортированного сканера без повторного открытия камеры"""
        if not self.is_enrolling: return
        
        # Читаем текущий кадр из общего потока сканера
        ret, frame = self.scanner.cam_thread.read()
        if not ret or frame is None: return
        
        # Извлекаем координаты лица, которые сканер ПРЯМО СЕЙЧАС держит в кэше
        locs_large = self.scanner.cached_locations
        
        if len(locs_large) == 1:
            rgb = np.ascontiguousarray(frame[:, :, ::-1])
            # Строим 128D вектор по точным координатам несжатого кадра
            enc = face_recognition.face_encodings(rgb, locs_large)[0]
            self.enroll_encodings.append(enc)
            
            self.enroll_stage_idx += 1
            self.flash_counter = 4 # Триггерим эффект затвора камеры
            
            stages = ["STRAIGHT", "UP", "UP-RIGHT", "RIGHT", "DOWN-RIGHT", "DOWN", "DOWN-LEFT", "LEFT", "UP-LEFT"]
            if self.enroll_stage_idx < 9:
                self.status_label.config(text=f"[{self.enroll_name}] TURN {stages[self.enroll_stage_idx]} | PRESS SPACE", fg=ACCENT)
            else:
                self.save_user_to_db()
        else:
            self.status_label.config(text="ERROR: TARGET FACE NOT MATCHED (Look straight at the camera)", fg=ERROR)

    def save_user_to_db(self):
        """Записывает 9 векторов лица в базу и отправляет сигнал логам"""
        conn = sqlite3.connect(core.DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (name, status) VALUES (?, ?)", (self.enroll_name, "friend"))
        uid = cursor.lastrowid
        for enc in self.enroll_encodings:
            cursor.execute("INSERT INTO encodings (user_id, encoding) VALUES (?, ?)", (uid, enc.tobytes()))
        conn.commit()
        conn.close()
        
        # Отправляем структурированный лог в общую таблицу
        core.log_event(uid, 100.0, "REG", f"Enrollment Completed: {self.enroll_name}")
        
        self.is_enrolling = False
        self.status_label.config(text=f"SUCCESS: {self.enroll_name} SAVED COMPLETED", fg=SUCCESS)
        
        # Каскадный хук: если мы запущены внутри дешборда, обновляем его таблицы на лету
        p = self.master
        while p:
            if hasattr(p, 'trigger_db_refresh'):
                p.trigger_db_refresh()
                break
            p = getattr(p, 'master', None)
        self.focus_force()

    def update_flash_effect(self):
        """Отрисовывает белый программный затвор при успешном снимке ракурса"""
        if self.flash_counter > 0:
            ret, frame = self.scanner.cam_thread.read()
            if ret and frame is not None:
                # Накладываем белую рамку затвора
                cv2.rectangle(frame, (0, 0), (frame.shape[1], frame.shape[0]), (255, 255, 255), 12)
                img = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                self.scanner.video_label.imgtk = img
                self.scanner.video_label.configure(image=img)
            self.flash_counter -= 1
        # Синхронизируем локальный таймер с циклом обновления Tkinter
        self.after(20, self.update_flash_effect)

    def shutdown(self):
        """Безопасный останов зависимого сканера при закрытии окна"""
        self.scanner.shutdown()

# Поддержка автономного запуска модуля (например, на компьютере HR-отдела)
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("700x580")
    root.configure(bg=BG_COLOR)
    root.title("STANDALONE REGISTRATION CLIENT")
    
    app = EnrollClientWidget(root)
    app.pack(fill=tk.BOTH, expand=True)
    
    root.protocol("WM_DELETE_WINDOW", lambda: [app.shutdown(), root.destroy()])
    root.mainloop()