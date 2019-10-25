import storage.sd_salt
from storage.sd_salt import (
    SD_CARD_HOT_SWAPPABLE,
    SdSaltError,
)
from trezor import io, ui
from trezor.ui.confirm import CONFIRMED, Confirm
from trezor.ui.text import Text

if False:
    from typing import Optional


class SdProtectCancelled(Exception):
    pass


async def _wrong_card_dialog() -> None:
    text = Text("SD card protection", ui.ICON_WRONG)
    text.bold("Wrong SD card.")
    text.br_half()
    if SD_CARD_HOT_SWAPPABLE:
        text.normal("Please insert the", "correct SD card for", "this device.")
        btn_confirm = "Retry"  # type: Optional[str]
        btn_cancel = "Abort"
    else:
        text.normal("Please unplug the", "device and insert the", "correct SD card.")
        btn_confirm = None
        btn_cancel = "Close"

    if await Confirm(text, confirm=btn_confirm, cancel=btn_cancel) is not CONFIRMED:
        raise SdProtectCancelled


async def _insert_card_dialog() -> None:
    text = Text("SD card protection", ui.ICON_WRONG)
    text.bold("SD card required.")
    text.br_half()
    if SD_CARD_HOT_SWAPPABLE:
        text.normal("Please insert your", "SD card.")
        btn_confirm = "Retry"  # type: Optional[str]
        btn_cancel = "Abort"
    else:
        text.normal("Please unplug the", "device and insert your", "SD card.")
        btn_confirm = None
        btn_cancel = "Close"

    if await Confirm(text, confirm=btn_confirm, cancel=btn_cancel) is not CONFIRMED:
        raise SdProtectCancelled


async def _sd_error_dialog(*args: str) -> None:
    text = Text("SD card protection", ui.ICON_WRONG, ui.RED)
    text.normal(*args)
    if await Confirm(text, confirm="Retry", cancel="Abort") is not CONFIRMED:
        raise OSError


async def ensure_sd_card() -> None:
    sd = io.SDCard()
    while not sd.power(True):
        await _insert_card_dialog()


async def request_sd_salt() -> Optional[bytearray]:
    while True:
        ensure_sd_card()
        try:
            return storage.sd_salt.load_sd_salt()
        except SdSaltError as e:
            if e.code == SdSaltError.CARD_MISMATCH:
                await _wrong_card_dialog()
            elif e.code == SdSaltError.READ_FAILED:
                await _sd_error_dialog("Failed to read from", "the SD card.")
            elif e.code == SdSaltError.WRITE_FAILED:
                await _sd_error_dialog("Failed to write data to", "the SD card.")
            else:
                raise RuntimeError  # non-exhaustive if/elif


async def set_sd_salt(salt: bytes, salt_tag: bytes, stage: bool = False) -> None:
    while True:
        ensure_sd_card()
        try:
            return storage.sd_salt.set_sd_salt(salt, salt_tag, stage)
        except SdSaltError as e:
            await _sd_error_dialog("Failed to write data to", "the SD card.")
