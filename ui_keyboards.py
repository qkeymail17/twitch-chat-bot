from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ui_constants import *
from ui_labels import (
    CHAT_HTML_LINK,
    CANCEL, VIDEO_DOWNLOAD
)


def build_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(CHAT_HTML_LINK, callback_data=CB_FMT_HTML_ONLINE),
            InlineKeyboardButton(VIDEO_DOWNLOAD, callback_data=CB_VID_DOWNLOAD)
        ],
        [
            InlineKeyboardButton(CANCEL, callback_data=CB_FORMAT_CANCEL),
        ]
    ])


def build_info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([])


def build_about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([])