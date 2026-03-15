from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ui_constants import *
from ui_labels import (
    CHAT_HTML_LINK, CHAT_HTML_FILE,
    CHAT_TXT_FILE, CHAT_CSV_FILE,
    CANCEL
)


def build_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(CHAT_HTML_LINK, callback_data=CB_FMT_HTML_ONLINE),
            InlineKeyboardButton(CHAT_HTML_FILE, callback_data=CB_FMT_HTML_LOCAL),
        ],
        [
            InlineKeyboardButton(CHAT_TXT_FILE, callback_data=CB_FMT_TXT),
            InlineKeyboardButton(CHAT_CSV_FILE, callback_data=CB_FMT_CSV),
        ],
        [
            InlineKeyboardButton(CANCEL, callback_data=CB_FORMAT_CANCEL),
        ]
    ])


def build_info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([])


def build_about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([])