# main_dashboard.py
import tkinter as tk
from tkinter import ttk
import core
from config import *
from admin_panel import AdminPanelWidget
from enroll_client import EnrollClientWidget

class MainEngineeringDashboard(tk.Tk):
    """
    RU: Корневой модуль СКУД. Агрегирует независимые виджеты СКУД и управляет единственным видеопотоком.
    EN: Master architecture node. Aggregates modular widgets and acts as the exclusive camera resource controller.
    """
    def __init__(self):
        super().__init__()
        core.init_db() # RU: Первичная сборка БД | EN: Initial database generation sequence
        
        self.geometry("1400x850")
        self.configure(bg=BG_COLOR)
        self.title("BIOMETRIC СКУД | MODULAR ENGINEERING DASHBOARD 12.1")
        
        # RU: МОНОПОЛЬНЫЙ ЗАХВАТ КАМЕРЫ: Запуск потока до конструирования UI модулей
        # EN: EXCLUSIVE HARDWARE CAPTURE: Spawns the thread device handle prior to modular UI building
        self.cam_thread = core.VideoCaptureThread(0).start()
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TPanedwindow', background=BG_COLOR)
        style.configure('TFrame', background=BG_COLOR)

        # RU: Главный разделитель окон Tkinter (PanedWindow) для горизонтального тайлинга
        # EN: Master Tkinter PanedWindow workspace container layout configuration (horizontal split)
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # ==============================================================================
        # ЛЕВАЯ ЧАСТЬ ИНТЕРФЕЙСА (ЛЕВЫЙ СЛОТ ТАЙЛИНГА)
        # ==============================================================================
        left_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=1)
        
        # RU: Встраивание виджета биометрической регистрации и liveness-сканирования
        # EN: Mount the biometric registration frame containing integrated liveness checks
        self.enroll_block = EnrollClientWidget(left_frame)
        self.enroll_block.pack(fill=tk.BOTH, expand=True)
        
        # ==============================================================================
        # ПРАВАЯ ЧАСТЬ ИНТЕРФЕЙСА (ПРАВЫЙ СЛОТ ТАЙЛИНГА)
        # ==============================================================================
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=1)
        
        # RU: Создание фабрики таблиц управления персоналом и системного аудита проходов
        # EN: Instantiate user data panel component interface framework factory
        self.admin_widget = AdminPanelWidget(right_frame)
        
        # RU: Сборка и размещение верхней таблицы базы данных пользователей
        # EN: Build and mount the top employee grid user table instance
        self.db_block = self.admin_widget.build_users_table(right_frame)
        self.db_block.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # RU: Сборка и размещение нижней таблицы логов верификации
        # EN: Build and mount the bottom runtime logs monitoring panel
        self.logs_block = self.admin_widget.build_logs_table(right_frame)
        self.logs_block.pack(fill=tk.BOTH, expand=True)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.lift()
        self.focus_force()

    # ==============================================================================
    # КАСКАДНЫЕ ХУКИ СИНХРОНИЗАЦИИ (INTER-WIDGET COMMUNICATIONS)
    # ==============================================================================

    def reload_vectors_trigger(self):
        """RU: Проброс сигнала очистки кэша векторов ОЗУ из админки в ядро сканера"""
        if hasattr(self.enroll_block, 'scanner'):
            self.enroll_block.scanner.reload_vectors()

    def trigger_log_refresh(self):
        """RU: Сигнал мгновенной перерисовки логов при генерации события внутри сканера лица"""
        self.admin_widget.refresh_logs_list()

    def trigger_db_refresh(self):
        """RU: Комплексная синхронизация модулей после успешной записи новой карточки сотрудника"""
        self.admin_widget.refresh_users_list()
        self.admin_widget.refresh_logs_list()
        if hasattr(self.enroll_block, 'scanner'):
            self.enroll_block.scanner.reload_vectors()

    def on_closing(self):
        """RU: Безопасный каскадный останов бесконечных потоков и освобождение видеодевайса V4L2"""
        if hasattr(self, 'enroll_block'):
            self.enroll_block.shutdown()
        if hasattr(self, 'cam_thread'):
            self.cam_thread.stop()
        self.destroy()

if __name__ == "__main__":
    app = MainEngineeringDashboard()
    app.mainloop()