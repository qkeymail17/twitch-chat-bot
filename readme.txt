Twitch VOD Chat Downloader Bot
PROJECT ARCHITECTURE MAP


========================
TABLE OF CONTENTS
========================

1. ЦЕЛЬ README
2. ARCHITECTURE DIAGRAM
3. USER FLOW
4. STATE MANAGEMENT
5. DOWNLOAD WORKER
6. TWITCH CHAT DOWNLOAD
7. FILE GENERATION
8. HTML GENERATION
9. CACHE SYSTEM
10. RESULT CARD
11. HISTORY SYSTEM
12. CALLBACK DATA FORMAT
13. FILE PURPOSE INDEX
14. DATA FLOW
15. EVENT FLOW
16. QUICK FLOW DIAGRAM


========================
ЦЕЛЬ README
========================

Этот файл нужен как карта проекта.

Он позволяет быстро понять:

- структуру проекта
- точки входа
- поток данных
- взаимосвязи модулей

README предназначен для быстрого восстановления контекста
без необходимости читать весь код проекта.
README описывает архитектуру проекта и может не отражать точную структуру файлов.



========================
ARCHITECTURE DIAGRAM
========================

                Telegram User
                       │
                       ▼
                vod_entry.py
                       │
                       ▼
                handlers_vod.py
                       │
                       ▼
                download_worker
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
        twitch_api           worker_writers
     (fetch_comments)        (txt / csv)
            │
            ▼
        messages
            │
            ▼
        worker_html
            │
            ▼
       html_renderer
            │
            ▼
         html file
            │
            ▼
       db_cache / db_history
            │
            ▼
       result card
            │
            ▼
     send_cached_files
            │
            ▼
        Telegram User



========================
USER FLOW
========================

1. Пользователь отправляет ссылку Twitch VOD

vod_entry.py

Из ссылки извлекается:

vod_id

Сохраняется pending состояние пользователя.

Пользователю показываются кнопки выбора формата.



2. Пользователь выбирает формат

handlers_vod.py

Проверяется:

busy состояние пользователя

После этого запускается worker загрузки.



========================
STATE MANAGEMENT
========================

handlers_state.py

set_pending(user_id, vod_id)
    сохраняет ожидающий VOD пользователя

set_busy(user_id, state)
    предотвращает запуск нескольких загрузок



========================
DOWNLOAD WORKER
========================

download_worker.download_and_send()

Главная функция загрузки.

Она:

1. скачивает чат
2. собирает статистику
3. генерирует файлы
4. возвращает meta, stats и files



========================
TWITCH CHAT DOWNLOAD
========================

twitch_api/fetch_comments.py

fetch_comments(vod_id)

Загружает весь чат стрима.

Использует:

twitch_api/fetch_page.py



fetch_page(cursor)

Загружает одну страницу сообщений.

Источник данных:

gql.twitch.tv



========================
FILE GENERATION
========================

worker_writers.py

Создаёт:

chat.txt
chat.csv



writers.py

Низкоуровневые функции записи файлов.



========================
HTML GENERATION
========================

worker_html.py

Подготавливает данные для HTML.



html_renderer.py

Генерирует HTML чат.

Использует:

templates/viewer_template.html


Режимы:

html_local
    эмоуты встроены base64

html_online
    эмоуты грузятся через CDN



========================
CACHE SYSTEM
========================

db_cache.py

Таблица cache:

cache_id
vod_id
format
meta
stats
files
html_url
created_at


Основные функции:

get_cache(vod_id, format)
get_cache_by_id(cache_id)
upsert_cache(...)



========================
RESULT CARD
========================

vod_format.py

_runner(...)

Сохраняет результат загрузки в cache
и формирует карточку результата.



_edit_progress_message_with_card(...)

Редактирует сообщение прогресса.



_send_card_with_buttons(...)

Отправляет карточку результата.



========================
HISTORY SYSTEM
========================

db_history.py

Хранит историю запросов пользователя.



history_callbacks.py

Обрабатывает кнопки истории.



history_files.py

send_cached_files(...)

Отправляет файлы из cache пользователю.



========================
CALLBACK DATA FORMAT
========================

Все callback константы находятся в:

ui_constants.py


Основные префиксы:

CB_FMT_TXT
CB_FMT_CSV
CB_FMT_HTML_ONLINE
CB_FMT_HTML_LOCAL


История:

CB_UI_HISTORY
CB_HIST_PAGE
CB_HIST_FILES_PREFIX
CB_HIST_VOD_PREFIX


Формат кнопки файлов:

ui:histfiles:{index}

index — индекс записи на странице истории.



========================
FILE PURPOSE INDEX
========================

ENTRY

vod_entry
    обработка входящих сообщений со ссылкой VOD

handlers_vod
    обработка кнопок выбора формата


CORE PIPELINE

download_worker
    загрузка чата и запуск генерации файлов

vod_format
    формирование карточки результата


STORAGE

db_cache
    кэш результатов

db_history
    история запросов пользователя


WORKERS

worker_writers
    генерация txt и csv

worker_html
    генерация HTML


API

twitch_api.*
    загрузка чата, метаданных и эмоутов Twitch


UI

ui_keyboards
ui_history
ui_constants


SUPPORT

worker_progress
    обновление прогресса загрузки

config
utils



========================
DEPENDENCY MAP
========================

Этот раздел показывает зависимости модулей проекта.
Стрелка означает: "модуль импортирует или вызывает".

Это помогает быстро понять архитектуру без просмотра всех файлов.



CORE FLOW

vod_entry
    ↓
handlers_vod
    ↓
download_worker
    ↓
vod_format
    ↓
history_files



WORKER PIPELINE

download_worker
    ↓
twitch_api.fetch_comments
    ↓
twitch_api.fetch_page

download_worker
    ↓
worker_writers
    ↓
writers

download_worker
    ↓
worker_html
    ↓
html_renderer



HTML VIEWER

worker_html
    ↓
html_renderer
    ↓
templates/viewer_template.html



CACHE SYSTEM

vod_format
    ↓
db_cache

history_callbacks
    ↓
db_cache

history_files
    ↓
db_cache



HISTORY SYSTEM

history_view
    ↓
db_history

history_callbacks
    ↓
db_history

history_files
    ↓
db_history



UI SYSTEM

handlers_vod
    ↓
ui_keyboards

ui_history
    ↓
ui_keyboards

ui_keyboards
    ↓
ui_constants

ui_history
    ↓
ui_formatters



STATE MANAGEMENT

vod_entry
    ↓
handlers_state

handlers_vod
    ↓
handlers_state

vod_cancel
    ↓
handlers_state



TWITCH API LAYER

twitch_api.fetch_comments
    ↓
twitch_api.fetch_page

twitch_api.fetch_comments
    ↓
twitch_api.emotes

twitch_api.fetch_comments
    ↓
twitch_api.meta

twitch_api.emotes
    ↓
twitch_api.twitch_global_emotes



PROGRESS SYSTEM

download_worker
    ↓
worker_progress



CONFIG / UTILS

большинство модулей
    ↓
config

вспомогательные функции
    ↓
utils




========================
DEPENDENCY SUMMARY
========================

Entry layer:
    vod_entry
    handlers_vod

Core pipeline:
    download_worker
    vod_format

Worker layer:
    worker_writers
    worker_html

API layer:
    twitch_api.*

Storage layer:
    db_cache
    db_history

UI layer:
    ui_keyboards
    ui_history
    ui_constants

Support layer:
    config
    utils



========================
PROJECT STRUCTURE
========================

twitch-downloader-bot/

    handlers_*.py
        Telegram handlers

    worker_*.py
        pipeline генерации файлов

    db_*.py
        работа с базой данных

    twitch_api/
        загрузка данных Twitch

    templates/
        HTML viewer



========================
DATA FLOW
========================

Twitch API
    ↓
fetch_comments
    ↓
messages
    ↓
stats + meta
    ↓
writers / html_renderer
    ↓
files
    ↓
db_cache
    ↓
result card
    ↓
send_cached_files
    ↓
Telegram user



========================
EVENT FLOW
========================

Telegram message
    ↓
vod_entry
    ↓
handlers_vod
    ↓
download_worker
    ↓
vod_format
    ↓
history_files
    ↓
send_cached_files



========================
QUICK FLOW DIAGRAM
========================

User
 ↓
Send VOD link
 ↓
Parse vod_id
 ↓
Download chat
 ↓
Generate files
 ↓
Save cache
 ↓
Show result
 ↓
Send files
