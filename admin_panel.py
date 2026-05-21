# admin_panel.py
import sys
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
import core
from config import *

class AdminPanelWidget(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG_COLOR)
        core.init_db()
        self.configure_styles()

    def configure_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Treeview", background=SURFACE_COLOR, foreground=TEXT_MAIN, fieldbackground=SURFACE_COLOR, font=FONT_SANS, rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background=BG_COLOR, foreground=TEXT_MUTED, font=FONT_MONO_BOLD, borderwidth=0)
        style.map("Treeview", background=[('selected', '#444444')], foreground=[('selected', TEXT_MAIN)])

    def build_users_table(self, parent_frame):
        """Создает и возвращает только блок управления пользователями (Верхняя часть)"""
        frame = tk.Frame(parent_frame, bg=BG_COLOR)
        tk.Label(frame, text="EMPLOYEES DATABASE MANAGEMENT", bg=BG_COLOR, fg=TEXT_MUTED, font=FONT_MONO_BOLD).pack(anchor=tk.W)
        
        self.user_tree = ttk.Treeview(frame, columns=("id", "name", "status"), show="headings")
        self.user_tree.heading("id", text="ID")
        self.user_tree.heading("name", text="NAME")
        self.user_tree.heading("status", text="STATUS")
        self.user_tree.column("id", width=40, anchor=tk.CENTER)
        self.user_tree.column("status", width=100, anchor=tk.CENTER)
        self.user_tree.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
        
        db_btn_frame = tk.Frame(frame, bg=BG_COLOR)
        db_btn_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Button(db_btn_frame, text="SET FRIEND", command=lambda: self.change_status("friend"), bg=SURFACE_COLOR, fg=TEXT_MAIN, bd=0, padx=10, pady=4).pack(side=tk.LEFT, padx=2)
        tk.Button(db_btn_frame, text="SET BLACKLIST", command=lambda: self.change_status("blacklist"), bg=SURFACE_COLOR, fg=TEXT_MAIN, bd=0, padx=10, pady=4).pack(side=tk.LEFT, padx=2)
        tk.Button(db_btn_frame, text="DELETE USER", command=self.delete_user, bg=SURFACE_COLOR, fg=TEXT_MUTED, bd=0, padx=10, pady=4).pack(side=tk.RIGHT, padx=2)
        
        self.refresh_users_list()
        return frame

    def build_logs_table(self, parent_frame):
        """Создает и возвращает только блок логов доступа (Нижняя часть)"""
        frame = tk.Frame(parent_frame, bg=BG_COLOR)
        tk.Label(frame, text="ACCESS LOGS HISTORY (REAL-TIME)", bg=BG_COLOR, fg=TEXT_MUTED, font=FONT_MONO_BOLD).pack(anchor=tk.W)
        
        self.log_tree = ttk.Treeview(frame, columns=("time", "name", "decision", "reason"), show="headings")
        self.log_tree.heading("time", text="TIMESTAMP")
        self.log_tree.heading("name", text="EMPLOYEE")
        self.log_tree.heading("decision", text="VERDICT")
        self.log_tree.heading("reason", text="REASON / LOG DETAILS")
        self.log_tree.column("time", width=130, anchor=tk.CENTER)
        self.log_tree.column("name", width=100, anchor=tk.W)
        self.log_tree.column("decision", width=70, anchor=tk.CENTER)
        self.log_tree.column("reason", width=180, anchor=tk.W)
        self.log_tree.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
        
        log_btn_frame = tk.Frame(frame, bg=BG_COLOR)
        log_btn_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Button(log_btn_frame, text="REFRESH LOGS", command=self.refresh_logs_list, bg=SURFACE_COLOR, fg=TEXT_MAIN, bd=0, padx=15, pady=4).pack(side=tk.LEFT, padx=2)
        tk.Button(log_btn_frame, text="CLEAR LOGS", command=self.clear_logs_history, bg=SURFACE_COLOR, fg=TEXT_MUTED, bd=0, padx=15, pady=4).pack(side=tk.RIGHT, padx=2)
        
        self.refresh_logs_list()
        return frame

    def refresh_users_list(self):
        for item in self.user_tree.get_children(): self.user_tree.delete(item)
        conn = sqlite3.connect(core.DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, status FROM users")
        for row in cursor.fetchall(): self.user_tree.insert("", tk.END, values=row)
        conn.close()

    def refresh_logs_list(self):
        for item in self.log_tree.get_children(): self.log_tree.delete(item)
        conn = sqlite3.connect(core.DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT l.timestamp, IFNULL(u.name, 'Unknown / Guest'), l.decision, l.reason 
            FROM logs l LEFT JOIN users u ON l.user_id = u.id ORDER BY l.id DESC
        """)
        for row in cursor.fetchall(): self.log_tree.insert("", tk.END, values=row)
        conn.close()

    def change_status(self, new_status):
        selected = self.user_tree.selection()
        if not selected: return
        user_id = self.user_tree.item(selected[0])['values'][0]
        conn = sqlite3.connect(core.DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id))
        conn.commit()
        conn.close()
        self.refresh_users_list()

        p = self.master
        while p and p != self:
            if hasattr(p, 'reload_vectors_trigger'):
                p.reload_vectors_trigger()
                break
            p = getattr(p, 'master', None)

    def clear_logs_history(self):
        if messagebox.askyesno("Database Maintenance", "Completely wipe ALL access logs from database?"):
            conn = sqlite3.connect(core.DB_NAME)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM logs")
            conn.commit()
            conn.close()
            self.refresh_logs_list()

    def delete_user(self):
        selected = self.user_tree.selection()
        if not selected: return
        user_id = self.user_tree.item(selected[0])['values'][0]
        if messagebox.askyesno("Warning", "Completely delete user and their access history?"):
            conn = sqlite3.connect(core.DB_NAME)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM encodings WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM logs WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            self.refresh_users_list()
            self.refresh_logs_list()

            p = self.master
            while p and p != self:
                if hasattr(p, 'reload_vectors_trigger'):
                    p.reload_vectors_trigger()
                    break
                p = getattr(p, 'master', None)