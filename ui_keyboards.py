from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ui_constants import *


def build_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 HTML ссылка", callback_data=CB_FMT_HTML_ONLINE),
            InlineKeyboardButton("📄 HTML файл", callback_data=CB_FMT_HTML_LOCAL),
        ],
        [
            InlineKeyboardButton("📝 TXT", callback_data=CB_FMT_TXT),
            InlineKeyboardButton("📊 CSV", callback_data=CB_FMT_CSV),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data=CB_PENDING_CANCEL),
        ]
    ])


def build_info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([])


def build_about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([])