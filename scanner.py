# scanner.py
import sys
import time
import cv2
import face_recognition
import numpy as np
import tkinter as tk
import queue
import threading
from scipy.spatial import distance as dist
from PIL import Image, ImageTk

import core
from config import *

class FaceScannerWidget(tk.Frame):
    """
    RU: Биометрическое ядро СКУД. Управляет стейт-машиной Liveness-анализа и воркером распознавания лиц.
    EN: Core biometric PACS element. Rules the Liveness state machine and the background face recognition loops.
    """
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, bg=BG_COLOR, *args, **kwargs)
        core.init_db()
        
        # RU: Инженерные константы и временные пороги СКУД
        # EN: Engine tuning parameters and system timeout metrics
        self.TRACKING_TIMEOUT = 2.50
        self.IDENTITY_LOCK_TIMEOUT = 2.50
        self.POSE_ASYMMETRY_THRESH = 1.45  
        self.threshold = 75.0
        
        # RU: Циклические ОЗУ-буферы для математического анализа временных рядов мимики Ивана
        # EN: Cyclic RAM buffers mapping feature variations for time-series biometric evaluations
        self.bio_ear_history = {}          # RU: Хронология EAR (Глаза) | EN: Eye Aspect Ratio tracker
        self.bio_smile_history = {}        # RU: Хронология Z-score губ | EN: Lips extension vector log
        self.bio_eye_positions = {}        # RU: Точки век (Анти-Палец) | EN: Absolute eye landmarks positions
        self.bio_cooldown_until = 0.0      # RU: Блокировка при атаке | EN: Spoofing defense sleep lockout timer
        
        # RU: Триггеры фиксации подтвержденных фаз мимических тестов
        # EN: Liveness validation state tracking components
        self.bio_recent_smiles = {}
        self.bio_recent_blinks = {}
        self.bio_liveness_passed = {}
        
        self.fps_frame_idx = 0
        self.last_face_seen_timestamp = 0.0
        self.last_tracked_identity = None
        self.last_tracked_timestamp = 0.0
        self.current_face_state = "NONE"
        
        # RU: Очереди межпоточного взаимодействия (Блокировка пула памяти кадров)
        # EN: Non-blocking inter-thread process queues for isolating memory heap frames allocation
        self.known_encodings, self.known_users = core.load_known_faces()
        self.recognition_queue = queue.Queue(maxsize=1) # RU: Вход нейросети | EN: Input pipeline queue
        self.results_queue = queue.Queue()             # RU: Выход нейросети | EN: Output pipeline queue
        self.is_recognizing = False
        
        # RU: Локальный кэш графических примитивов отрисовки (Исключает мерцание интерфейса)
        # EN: UI local drawing layer caching arrays (Eliminates runtime interface flickering)
        self.cached_locations = []
        self.cached_identities = []
        self.cached_names = []
        self.cached_colors = []
        self.cached_landmarks = []

        # RU: ПОИСК СКВОЗНОГО РОДИТЕЛЬСКОГО ПОТОКА КАМЕРЫ (ЗАЩИТА ОТ ДВОЙНОГО ОТКРЫТИЯ /dev/video0)
        # EN: ARCHITECTURAL CAMERA BUS DISCOVERY (PREVENTS SYSTEM CONFLICTS OVER DEVICE PIN)
        main_cam_source = None
        curr_node = parent
        while curr_node:
            if hasattr(curr_node, 'cam_thread') and curr_node.cam_thread is not None:
                main_cam_source = curr_node.cam_thread
                break
            curr_node = getattr(curr_node, 'master', None)

        if main_cam_source:
            self.cam_thread = main_cam_source
        else:
            self.cam_thread = core.VideoCaptureThread(0).start()
        
        self.video_label = tk.Label(self, bg=BG_COLOR, bd=0)
        self.video_label.pack(fill=tk.BOTH, expand=True)
        
        # RU: Запуск параллельного изолированного потока инференса дескрипторов лиц
        # EN: Spawn isolated long-running background daemon thread for face embeddings extraction
        threading.Thread(target=self.face_recognition_worker, daemon=True).start()
        self.update_scanner()

    def reload_vectors(self):
        self.known_encodings, self.known_users = core.load_known_faces()

    def face_recognition_worker(self):
        """
        RU: Изолированный поток инференса dlib. Выполняет HOG-локализацию и кодирование 128D вектора.
        EN: Isolated dlib inference loop. Performs heavy HOG localization and 128D descriptors extraction.
        """
        while True:
            rgb_full_frame = self.recognition_queue.get() # RU: Извлечение кадра | EN: Read queue chunk
            if rgb_full_frame is None: break
            
            # RU: Оптимизация скорости: поиск координат лица на сжатом в 2 раза кадре
            # EN: Speed optimization block: search face coordinates on a 0.5x scaled down frame matrix
            small_frame = cv2.resize(rgb_full_frame, (0, 0), fx=0.5, fy=0.5)
            loc_small = face_recognition.face_locations(small_frame, model="hog")
            # RU: Трансляция координат окна обратно в исходный размер 640x480 (Без потери точности вектора)
            # EN: Project vector boundaries back onto the native uncompressed 640x480 frame space
            loc_large = [(t*2, r*2, b*2, l*2) for (t, r, b, l) in loc_small]
            
            identities = []
            if loc_large:
                # RU: Тяжелый расчет дескрипторов лица на исходном несжатом кадре
                # EN: Compute high-precision facial features descriptors on the native raw frame data
                face_encodings = face_recognition.face_encodings(rgb_full_frame, loc_large)
                for face_encoding in face_encodings:
                    identity = {"id": None, "name": "Unknown", "status": "unknown", "percent": 0.0}
                    if self.known_encodings:
                        # RU: Вычисление евклидова расстояния до всех эталонов в ОЗУ
                        # EN: Compute Euclidean spatial vector distances across all preloaded profiles
                        dists = face_recognition.face_distance(self.known_encodings, face_encoding)
                        b_idx = np.argmin(dists)
                        min_dist = dists[b_idx]
                        if min_dist < 0.48: # RU: Порог отсечения СКУД | EN: PACS distance confidence filter
                            percent = round(max(0, 100 - (min_dist / 0.48) * 40), 1)
                            if percent >= self.threshold:
                                identity["id"] = self.known_users[b_idx][0]
                                identity["name"] = self.known_users[b_idx][1]
                                identity["status"] = self.known_users[b_idx][2]
                                identity["percent"] = percent
                    identities.append(identity)
            # RU: Передача результатов в поток отрисовки | EN: Direct calculation data drop to results UI queue
            self.results_queue.put((loc_large, identities))
            self.recognition_queue.task_done()

    def update_scanner(self):
        """
        RU: Основной поток обработки кадров СКУД. Содержит стейт-машину Liveness-тестов.
        EN: Master PACS frame processor. Contains the dynamic multi-stage Liveness state engine.
        """
        ret, frame = self.cam_thread.read()
        if not ret or frame is None:
            self.after(15, self.update_scanner)
            return
        
        self.fps_frame_idx += 1
        current_time = time.time()
        rgb_full_frame = np.ascontiguousarray(frame[:, :, ::-1])
        
        # ==============================================================================
        # БЛОК ИЗВЛЕЧЕНИЯ И КАСКАДНОЙ ФИЛЬТРАЦИИ ИДЕНТИФИКАЦИИ ИЗ ОЧЕРЕДИ
        # ==============================================================================
        try:
            locations, identities = self.results_queue.get_nowait()
            if locations is not None and len(locations) > 0:
                self.cached_locations = locations
                
                # RU: Менеджер коллизий: один ID в кадре - у кого процент совпадения выше (Winner-Takes-All)
                # EN: Conflict management pipeline: mapped IDs locked to unique higher accuracy rating match entries
                id_to_best_idx = {}
                for i, identity in enumerate(identities):
                    uid = identity["id"]
                    if uid is not None:
                        if uid not in id_to_best_idx or identity["percent"] > identities[id_to_best_idx[uid]]["percent"]:
                            id_to_best_idx[uid] = i
                
                processed_identities = []
                for i, identity in enumerate(identities):
                    uid = identity["id"]
                    if uid is not None and id_to_best_idx[uid] != i:
                        identity = {"id": None, "name": "Unknown", "status": "unknown", "percent": 0.0}
                    
                    if identity["name"] != "Unknown":
                        self.last_tracked_identity = identity.copy()
                        self.last_tracked_timestamp = current_time
                    processed_identities.append(identity)
                
                self.cached_identities = processed_identities
                self.last_face_seen_timestamp = current_time
            else:
                # RU: Реализация инерции имени: удерживаем трек Ивана 800мс, если он моргнул или смазал мимику
                # EN: Runtime name inertia: locks targeted user identity tracking profile context window for 800ms
                if self.last_tracked_identity and (current_time - self.last_tracked_timestamp) < 0.8:
                    if self.cached_locations:
                        self.last_face_seen_timestamp = current_time
                else:
                    self.cached_locations = []
                    self.cached_identities = []
                    
            self.is_recognizing = False
        except queue.Empty: pass

        # RU: Дросселирование нейросети: отправка кадра на анализ каждый 4-й фрейм вебкамеры
        # EN: Framework network frame throttling: push source frame array to input workspace queue every 4th cycle
        if self.fps_frame_idx % 4 == 0 and not self.is_recognizing:
            if self.recognition_queue.empty():
                self.is_recognizing = True
                self.recognition_queue.put(rgb_full_frame)

        # ==============================================================================
        # ЛОГИКА ТАЙМАУТА ПОТЕРИ ЛИЦА (STATE-MACHINE LOST TRIGGER)
        # ==============================================================================
        is_tracking_active = (current_time - self.last_face_seen_timestamp) < self.TRACKING_TIMEOUT
        if not self.cached_locations or not is_tracking_active:
            if self.current_face_state != "NONE" and not is_tracking_active:
                core.log_event(None, 0.0, "LOST", "Face left camera view")
                self.current_face_state = "NONE"
                # RU: Зачистка ОЗУ-контекста текущей сессии
                # EN: Instantly purge temporary evaluation vectors history and memory context blocks
                self.bio_ear_history, self.bio_smile_history, self.bio_eye_positions = {}, {}, {}
                self.bio_recent_smiles, self.bio_recent_blinks, self.bio_liveness_passed = {}, {}, {}
                self.cached_locations, self.cached_identities = [], []
                self.last_tracked_identity = None
                
                # RU: Каскадный хук перерисовки таблицы логов в главном окне дешборда
                # EN: Signal bubbling loop to immediately update dashboard event tracking boards
                p = self.master
                while p and p != self:
                    if hasattr(p, 'trigger_log_refresh'): p.trigger_log_refresh(); break
                    p = getattr(p, 'master', None)

        # ==============================================================================
        # СТРУКТУРНЫЙ АНАЛИЗ ГЕОМЕТРИИ ЛИЦА И РАСЧЕТ АНТИ-СПОФИНГА
        # ==============================================================================
        self.cached_names, self.cached_colors = [], []
        if self.cached_locations:
            # RU: Извлечение 68 ключевых точек геометрии лица (Landmarks)
            # EN: Extract 68 critical spatial facial point coordinates mappings vectors array
            landmarks = face_recognition.face_landmarks(rgb_full_frame, self.cached_locations)
            if landmarks: self.cached_landmarks = landmarks
            
            for i, identity in enumerate(self.cached_identities):
                if i >= len(self.cached_locations): break
                d_name = identity["name"]
                
                is_known = (d_name != "Unknown") or (self.last_tracked_identity is not None and (current_time - self.last_tracked_timestamp) < 0.8)
                if is_known and self.last_tracked_identity:
                    d_name = self.last_tracked_identity["name"]
                    identity = self.last_tracked_identity
                
                b_color, b_name = (128, 128, 128), "Unknown"
                is_head_turned = False
                
                if i < len(self.cached_landmarks):
                    marks = self.cached_landmarks[i]
                    
                    # 1. АНАТОМИЧЕСКИЙ ФИЛЬТР ПОВОРОТА ГОЛОВЫ (АСИММЕТРИЯ ПРОЕКЦИИ)
                    if 'left_eye' in marks and 'right_eye' in marks and 'nose_bridge' in marks:
                        dist_left = dist.euclidean(marks['left_eye'][0], marks['nose_bridge'][0])
                        dist_right = dist.euclidean(marks['right_eye'][3], marks['nose_bridge'][0])
                        asymmetry = max(dist_left, dist_right) / max(min(dist_left, dist_right), 0.1)
                        if asymmetry > self.POSE_ASYMMETRY_THRESH:
                            is_head_turned = True
                            
                            # RU: Обход: разрешаем поворот, если этот экземпляр сканера запущен внутри окна регистрации
                            # EN: Intercept check: clear head turning block parameter flags if node parent is EnrollClientWidget
                            p = self.master
                            while p and p != self:
                                from enroll_client import EnrollClientWidget
                                if isinstance(p, EnrollClientWidget) and p.is_enrolling:
                                    is_head_turned = False
                                    break
                                p = getattr(p, 'master', None)
                    
                    # ==============================================================================
                    # КОМПЛЕКС ВЕРИФИКАЦИИ ЖИВОГО ЧЕЛОВЕКА (LIVENESS ENGINE PIPELINE)
                    # ==============================================================================
                    if is_known and not is_head_turned and current_time > self.bio_cooldown_until:
                        if 'left_eye' in marks and 'right_eye' in marks and 'top_lip' in marks and 'bottom_lip' in marks:
                            
                            # RU: БАЗИС ИНВАРИАНТНОСТИ К МАСШТАБУ: расстояние между уголками глаз
                            # EN: GEOMETRIC BASIS DEVIATION CORRECTION: spatial vector distance spanning outer eye bounds
                            face_basis = dist.euclidean(marks['left_eye'][0], marks['right_eye'][3])
                            face_basis = max(face_basis, 1.0)
                            
                            ear = (core.eye_aspect_ratio(marks['left_eye']) + core.eye_aspect_ratio(marks['right_eye'])) / 2.0
                            c_width, mar = core.analyze_smile_geometry(marks['top_lip'] + marks['bottom_lip'])
                            norm_smile = c_width / face_basis # RU: Нормирование улыбки | EN: Normalized width factor mapping
                            
                            current_eye_pos = np.array(marks['left_eye'] + marks['right_eye'])
                            
                            # RU: Наполнение кольцевых буферов хронологии параметров
                            # EN: Push values data directly into system temporal analytics memory logs
                            if d_name not in self.bio_ear_history: self.bio_ear_history[d_name] = []
                            if d_name not in self.bio_smile_history: self.bio_smile_history[d_name] = []
                            if d_name not in self.bio_eye_positions: self.bio_eye_positions[d_name] = []
                            
                            self.bio_ear_history[d_name].append(ear)
                            self.bio_smile_history[d_name].append(norm_smile)
                            self.bio_eye_positions[d_name].append(current_eye_pos)
                            
                            if len(self.bio_ear_history[d_name]) > 40: self.bio_ear_history[d_name].pop(0)
                            if len(self.bio_smile_history[d_name]) > 40: self.bio_smile_history[d_name].pop(0)
                            if len(self.bio_eye_positions[d_name]) > 5: self.bio_eye_positions[d_name].pop(0)
                            
                            if len(self.bio_ear_history[d_name]) >= 12:
                                ear_arr = np.array(self.bio_ear_history[d_name])
                                smile_arr = np.array(self.bio_smile_history[d_name])
                                
                                # А) ЦЕНЗ ТЕКСТУРЫ КОЖИ LBP (ЗАЩИТА ОТ ЭКРАНОВ ТЕЛЕФОНОВ / REPLAY ATTACK)
                                texture_points = marks['left_eye'] + marks['right_eye'] + marks['nose_bridge']
                                is_genuine_skin = core.analyze_texture_lbp(frame, texture_points)
                                
                                if is_genuine_skin:
                                    # Б) Eye Continuity Guard: Если точки век скакнули > 14 пикселей (перекрытие пальцем) - бан сессии
                                    # EN: Eye Continuity Guard: Anomalous point shift step delta > 14px triggers active input freeze
                                    is_eye_continuous = True
                                    if len(self.bio_eye_positions[d_name]) >= 2:
                                        jump = np.max(np.abs(self.bio_eye_positions[d_name][-1] - self.bio_eye_positions[d_name][-2]))
                                        if jump > 14.0: is_eye_continuous = False
                                    
                                    if is_eye_continuous:
                                        ear_median = np.median(ear_arr)
                                        # RU: Моргание - падение EAR ниже 76% от индивидуальной скользящей медианы Ивана
                                        # EN: Blink sequence verification: current EAR value drop below 76% threshold level
                                        if ear < (ear_median * 0.76):  
                                            self.bio_recent_blinks[d_name] = current_time
                                    else:
                                        # RU: Палец обнаружен: аварийный сброс буферов и штрафной таймаут
                                        # EN: Occlusion detected: lock tracking context and enforce penalty cooldown window
                                        self.bio_cooldown_until = current_time + 1.5
                                        self.bio_ear_history[d_name] = []
                                    
                                    # В) УЛЫБКА: Оценка отклонения Z-score относительно личной дисперсии рта человека
                                    # EN: SMILE VERIFICATION: Analytical evaluation of current data displacement variance via Z-score
                                    smile_mean = np.mean(smile_arr[:-1])
                                    smile_std = np.std(smile_arr[:-1])
                                    
                                    if smile_std > 0.0001:
                                        z_score = (norm_smile - smile_mean) / smile_std
                                        # RU: Живой мимический всплеск ($Z > 2.0$) при условии закрытых зубов ($mar < 0.25$)
                                        # EN: Muscle acceleration burst threshold check ($Z > 2.0$) with mouth closure verified ($mar < 0.25$)
                                        if z_score > 2.0 and mar < 0.25:
                                            self.bio_recent_smiles[d_name] = current_time
                                else:
                                    self.bio_smile_history[d_name] = []

                # RU: Временной кластер: оба жеста должны быть зафиксированы в окне 2.5 секунды
                # EN: Temporal clustering logic check: track both actions markers flags validity across a strict 2.5s window
                has_smiled_recently = (current_time - self.bio_recent_smiles.get(d_name, 0)) < 2.5
                has_blinked_recently = (current_time - self.bio_recent_blinks.get(d_name, 0)) < 2.5
                if has_smiled_recently and has_blinked_recently: self.bio_liveness_passed[d_name] = True
                
                # ==============================================================================
                # УПРАВЛЕНИЕ СТЕЙТ-МАШИНОЙ И ЗАПИСЬ ЖУРНАЛОВ СКУД (DASHBOARD STATE SYNCHRONIZATION)
                # ==============================================================================
                has_passed_liveness = self.bio_liveness_passed.get(d_name, False)
                if i == 0:
                    if is_known:
                        if not has_passed_liveness:
                            if self.current_face_state != "WAITING_SYNC":
                                core.log_event(identity["id"], identity["percent"], "WAIT", "Awaiting gestures")
                                self.current_face_state = "WAITING_SYNC"
                                p = self.master
                                while p and p != self:
                                    if hasattr(p, 'trigger_log_refresh'): p.trigger_log_refresh(); break
                                    p = getattr(p, 'master', None)
                        else:
                            if self.current_face_state != "KNOWN":
                                verdict = "AUTH" if identity["status"] == "friend" else "BAN"
                                core.log_event(identity["id"], identity["percent"], verdict, "Verification Passed")
                                self.current_face_state = "KNOWN"
                                p = self.master
                                while p and p != self:
                                    if hasattr(p, 'trigger_log_refresh'): p.trigger_log_refresh(); break
                                    p = getattr(p, 'master', None)
                    else:
                        if self.current_face_state != "UNKNOWN":
                            core.log_event(None, identity["percent"], "UNK", "Unknown face detected")
                            self.current_face_state = "UNKNOWN"
                            p = self.master
                            while p and p != self:
                                if hasattr(p, 'trigger_log_refresh'): p.trigger_log_refresh(); break
                                p = getattr(p, 'master', None)
                
                # RU: Формирование текстовых маркеров подсказок СКУД для вывода на холст
                # EN: Structural orchestration of tracking metadata text and color variables for HUD display
                if is_known:
                    if current_time < self.bio_cooldown_until:
                        b_name = "LOCKOUT: COUNTER-SPOOFING"
                        b_color = (0, 0, 160)
                    elif not has_passed_liveness:
                        b_name = "NOW BLINK" if has_smiled_recently else ("NOW SMILE" if has_blinked_recently else "SMILE & BLINK")
                        b_color = (128, 128, 128)
                    else:
                        b_name = f"{d_name} ({identity['percent']}%)" if identity['status'] == "friend" else f"BAN: {d_name}"
                        b_color = (255, 255, 255) if identity['status'] == "friend" else (44, 44, 44)
                self.cached_names.append(b_name)
                self.cached_colors.append(b_color)
                
            # ==============================================================================
            # ГРАФИЧЕСКИЙ РЕНДЕРИНГ ЭЛЕМЕНТОВ ИНТЕРФЕЙСА (OPENCV HUD OVERLAYS)
            # ==============================================================================
            for (top, right, bottom, left), name, color in zip(self.cached_locations, self.cached_names, self.cached_colors):
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                cv2.rectangle(frame, (left, bottom - 25), (right, bottom), color, cv2.FILLED)
                cv2.putText(frame, name, (left + 6, bottom - 8), cv2.FONT_HERSHEY_DUPLEX, 0.45, (0, 0, 0), 1)

        # RU: Перенос массива байт OpenCV в растровый графический холст интерфейса Tkinter
        # EN: Package raw processed OpenCV array bytes back into Tkinter PhotoImage textures conversion
        img = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        self.video_label.imgtk = img
        self.video_label.configure(image=img)
        self.after(15, self.update_scanner)

    def shutdown(self):
        if hasattr(self, 'cam_thread') and self.cam_thread.started:
            p = self.master
            is_external = False
            while p and p != self:
                if hasattr(p, 'cam_thread') and p.cam_thread == self.cam_thread: is_external = True; break
                p = getattr(p, 'master', None)
            if not is_external: self.cam_thread.stop()
        self.recognition_queue.put(None)

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("700x500")
    root.title("STANDALONE SCANNER GATE")
    app = FaceScannerWidget(root)
    app.pack(fill=tk.BOTH, expand=True)
    root.protocol("WM_DELETE_WINDOW", lambda: [app.shutdown(), root.destroy()])
    root.mainloop()