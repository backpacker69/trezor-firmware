from trezor import wire
from trezor.messages.ApplyFlags import ApplyFlags
from trezor.messages.Success import Success

from apps.common.storage.device import set_flags


async def apply_flags(ctx: wire.Context, msg: ApplyFlags) -> Success:
    set_flags(msg.flags)
    return Success(message="Flags applied")
