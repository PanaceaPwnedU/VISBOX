ENGLISH TEXT BELOW

VISBOX — биометрическая система контроля доступа (СКУД) с многоуровневой защитой от подделки биометрии (Anti-Spoofing). Работает на стандартных RGB-камерах без использования датчиков глубины или ИК-сенсоров.
Технологический стек и принцип работы

    Базовые библиотеки: OpenCV (захват и обработка видеопотока), dlib / face_recognition (локализация лиц, детекция 68 ключевых точек и генерация 128-мерных векторов-слепков).

    Алгоритмы Liveness Detection: 3D-нормализация пропорций лица относительно расстояния между глазами (защита от наклонов фото), текстурный анализатор микроструктуры кожи LBP (отсекает пиксельные решетки экранов смартфонов и муар), статистический Z-score анализ скорости мимики (отличает живую улыбку от поворота телефона) и Eye Continuity Guard (блокирует симуляцию моргания при перекрытии глаз пальцами).

    База данных: SQLite в режиме WAL (Write-Ahead Logging) для потокобезопасной асинхронной записи логов и хранения бинарных шаблонов лиц.

Совместимость с ОС

Система кроссплатформенная и запускается на:

    Linux (Arch Linux, EndeavourOS, Manjaro, Ubuntu, Debian и др.).

    Windows (требуются инструменты сборки C++).

Краткий разбор внутренних модулей

    main_dashboard.py: Главное окно приложения. Запускает единый фоновый поток камеры и объединяет в один интерфейс сканер, панель управления и логи.

    scanner.py: Интеллектуальное ядро. Занимается непрерывным сканированием видеопотока, запускает асинхронную нейросетевую верификацию и контролирует прохождение тестов "улыбнись и моргни".

    enroll_client.py: Модуль регистрации. Позволяет оператору завести нового сотрудника, пошагово захватив лицо под 9 разными углами для создания точного эталонного шаблона в базе.

    admin_panel.py: Панель администратора. Управляет базой данных сотрудников (CRUD-операции, переключение прав доступа Friend / Blacklist) и выводит в реальном времени журнал событий прохода.

    core.py: Низкоуровневый вычислительный бэкенд. Отвечает за многопоточный захват видеопотока, математику EAR/MAR и транзакции СУБД.

    config.py: Файл конфигурации, содержащий параметры цветовой схемы графического интерфейса и пороговые значения фильтров liveness-анализа.

English (VISBOX Description)

VISBOX is a biometric access control framework featuring a multi-tiered liveness detection (Anti-Spoofing) pipeline. Engineered to operate on standard RGB webcams without relying on infrared sensors or depth hardware.
Tech Stack & Core Mechanics

    Core Libraries: OpenCV (video stream acquisition and image rendering), dlib / face_recognition (face localization, 68-landmark detection, and 128D facial vector embedding generation).

    Liveness Detection Algorithms: 3D facial feature normalization relative to the outer eye-to-eye distance (ensures scale and rotation invariance), Local Binary Patterns (LBP) descriptor evaluating micro-texture frequency (filters out smartphone display grids and moiré), statistical Z-score velocity analysis (isolates live muscle acceleration from smooth photo rotations), and the Eye Continuity Guard (aborts verification if eye landmarks are compromised by manual occlusion like fingers).

    Database Backend: SQLite optimized with Write-Ahead Logging (WAL mode) for high-speed, thread-safe asynchronous logging and profile binary vector storage.

Target Environments

The system is cross-platform and compiles smoothly on:

    Linux (Arch Linux, EndeavourOS, Manjaro, Ubuntu, Debian, etc.).

    Windows (requires native C++ compiler toolchains installed).

Structural Layout of Internal Modules

    main_dashboard.py: Application entry point. Instantiates the thread-safe global video stream capture and orchestrates scanner sub-widgets, admin panels, and history logs into a single window layout.

    scanner.py: Biometric processing unit. Handles continuous tracking, isolates background identification threads, and updates state machines tracking the "smile and blink" validation sequences.

    enroll_client.py: Registration terminal module. Guides operators through onboarding routines by sequentially logging 9 discrete facial perspectives to construct an immutable database reference target.

    admin_panel.py: Data management dashboard. Provides CRUD transaction utilities, overrides profile state configurations (Friend / Blacklist updates), and hosts a real-time system event monitor.

    core.py: Low-level computational backend. Directly executes multi-threaded camera grab loops, manages mathematical metric calculations (EAR/MAR), and serves transactional database inputs.

    config.py: System configuration matrix containing color variables for the graphical dark theme and constraints adjustments for anti-spoofing logic parameters.
