from trezor import ui, wire
from trezor.messages import ButtonRequestType
from trezor.messages.Success import Success
from trezor.messages.WipeDevice import WipeDevice
from trezor.ui.button import ButtonCancel
from trezor.ui.loader import LoaderDanger
from trezor.ui.text import Text

from apps.common import storage
from apps.common.confirm import require_hold_to_confirm


async def wipe_device(ctx: wire.Context, msg: WipeDevice) -> Success:
    text = Text("Wipe device", ui.ICON_WIPE, ui.RED)
    text.normal("Do you really want to", "wipe the device?", "")
    text.bold("All data will be lost.")
    await require_hold_to_confirm(
        ctx,
        text,
        ButtonRequestType.WipeDevice,
        confirm_style=ButtonCancel,
        loader_style=LoaderDanger,
    )

    storage.wipe()

    return Success(message="Device wiped")
