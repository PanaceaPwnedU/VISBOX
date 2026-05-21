# core.py
import sqlite3
import time
from datetime import datetime
import cv2
import face_recognition
import numpy as np
import threading
from scipy.spatial import distance as dist

DB_NAME = "biometrics.db"

def eye_aspect_ratio(eye):
    A = dist.euclidean(eye[1], eye[5])
    B = dist.euclidean(eye[2], eye[4])
    C = dist.euclidean(eye[0], eye[3])
    return (A + B) / (2.0 * C)

def analyze_smile_geometry(mouth):
    left_corner = mouth[0]
    right_corner = mouth[6]
    top_lip_top = mouth[3]
    bottom_lip_bottom = mouth[9]
    
    width = dist.euclidean(left_corner, right_corner)
    height = dist.euclidean(top_lip_top, bottom_lip_bottom)
    mar = height / max(width, 1.0)
    return width, mar

def analyze_texture_lbp(image, box_points):
    """
    Промышленный анализатор микротекстуры (LBP).
    Выявляет структуру пиксельной сетки экранов (муар) и матовость распечатанной бумаги.
    """
    try:
        pts = np.array(box_points, dtype=np.int32)
        x, y, w, h = cv2.boundingRect(pts)
        if w < 10 or h < 10: return False
        
        roi = image[y:y+h, x:x+w]
        if roi.size == 0: return False
        
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (32, 32))
        
        # Вычисляем локальные бинарные паттерны для матрицы 32x32
        lbp = np.zeros_like(gray)
        for i in range(1, 31):
            for j in range(1, 31):
                center = gray[i, j]
                code = 0
                code |= (gray[i-1, j-1] >= center) << 7
                code |= (gray[i-1, j]   >= center) << 6
                code |= (gray[i-1, j+1] >= center) << 5
                code |= (gray[i, j+1]   >= center) << 4
                code |= (gray[i+1, j+1] >= center) << 3
                code |= (gray[i+1, j]   >= center) << 2
                code |= (gray[i+1, j-1] >= center) << 1
                code |= (gray[i, j-1]   >= center) << 0
                lbp[i, j] = code
                
        hist, _ = np.histogram(lbp.flatten(), bins=256, range=(0, 256), density=True)
        
        # Живая кожа имеет высокую энтропию в средних частотах. 
        # Экраны телефонов дают резкие пики из-за интерференции субпикселей.
        max_peak = np.max(hist)
        if max_peak > 0.18 or hist[0] > 0.25: 
            return False # Спуфинг: искусственный паттерн
        return True # Живая кожа
    except:
        return False

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.executescript("""
        PRAGMA synchronous = OFF;
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS encodings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, encoding BLOB NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, timestamp DATETIME, match_percent REAL, decision TEXT, reason TEXT);
    """)
    conn.commit()
    conn.close()

def load_known_faces():
    known_encodings = []
    known_users = []
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT u.id, u.name, u.status, e.encoding FROM users u JOIN encodings e ON u.id = e.user_id")
    for row in cursor.fetchall():
        known_users.append((row[0], row[1], row[2]))
        known_encodings.append(np.frombuffer(row[3], dtype=np.float64))
    conn.close()
    return known_encodings, known_users

def log_event(user_id, match_percent, decision, reason):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO logs (user_id, timestamp, match_percent, decision, reason) VALUES (?, ?, ?, ?, ?)", 
                   (user_id, timestamp, match_percent, decision, reason))
    conn.commit()
    conn.close()

class VideoCaptureThread:
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.ret, self.frame = self.stream.read()
        self.started = False
        self.read_lock = threading.Lock()

    def start(self):
        if self.started: return self
        self.started = True
        self.thread = threading.Thread(target=self.update, args=(), daemon=True)
        self.thread.start()
        return self

    def update(self):
        while self.started:
            ret, frame = self.stream.read()
            if ret:
                with self.read_lock:
                    self.ret = ret
                    self.frame = frame
            time.sleep(0.01)

    def read(self):
        with self.read_lock:
            return self.ret, self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.started = False
        if self.stream.isOpened():
            self.stream.release()