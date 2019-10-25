import storage.sd_salt
from trezor import config, ui, wire
from trezor.crypto import hmac, random
from trezor.crypto.hashlib import sha256
from trezor.messages import SdProtectOperationType
from trezor.messages.Success import Success
from trezor.pin import pin_to_int
from trezor.ui.text import Text

from apps.common.confirm import require_confirm
from apps.common.layout import show_success
from apps.common.request_pin import (
    request_pin_ack,
    request_pin_and_sd_salt,
    show_pin_invalid,
)
from apps.common.sd_salt import ensure_sd_card, set_sd_salt

if False:
    from trezor.messages.SdProtect import SdProtect


def _make_salt():
    salt = random.bytes(storage.sd_salt.SD_SALT_LEN_BYTES)
    auth_key = random.bytes(storage.sd_salt.SD_SALT_AUTH_KEY_LEN_BYTES)
    tag = storage.sd_salt.compute_auth_tag(salt, auth_key)
    return salt, auth_key, tag


async def sd_protect(ctx: wire.Context, msg: SdProtect) -> Success:
    if not storage.is_initialized():
        raise wire.NotInitialized("Device is not initialized")

    if msg.operation == SdProtectOperationType.ENABLE:
        return await sd_protect_enable(ctx, msg)
    elif msg.operation == SdProtectOperationType.DISABLE:
        return await sd_protect_disable(ctx, msg)
    elif msg.operation == SdProtectOperationType.REFRESH:
        return await sd_protect_refresh(ctx, msg)
    else:
        raise wire.ProcessError("Unknown operation")


async def sd_protect_enable(ctx: wire.Context, msg: SdProtect) -> Success:
    if storage.sd_salt.is_sd_salt_enabled():
        raise wire.ProcessError("SD card protection already enabled")

    # Confirm that user wants to proceed with the operation.
    await require_confirm_sd_protect(ctx, msg)

    # Get the current PIN.
    if config.has_pin():
        pin = pin_to_int(await request_pin_ack(ctx, "Enter PIN", config.get_pin_rem()))
    else:
        pin = pin_to_int("")

    # Check PIN and prepare salt file.
    salt, salt_auth_key, salt_tag = _make_salt()
    await set_sd_salt(salt, salt_tag)

    if not config.change_pin(pin, pin, None, salt):
        # Wrong PIN. Clean up the prepared salt file.
        try:
            storage.sd_salt.remove_sd_salt()
        except Exception:
            # The cleanup is not necessary for the correct functioning of
            # SD-protection. If it fails for any reason, we suppress the
            # exception, because primarily we need to raise wire.PinInvalid.
            pass
        await show_pin_invalid(ctx)
        raise wire.PinInvalid("PIN invalid")

    storage.sd_salt.set_auth_key(salt_auth_key)

    await show_success(ctx, ("You have successfully", "enabled SD protection."))
    return Success(message="SD card protection enabled")


async def sd_protect_disable(ctx: wire.Context, msg: SdProtect) -> Success:
    if not storage.sd_salt.is_sd_salt_enabled():
        raise wire.ProcessError("SD card protection not enabled")

    # Confirm that user wants to proceed with the operation.
    await require_confirm_sd_protect(ctx, msg)

    # Get the current PIN and salt from the SD card.
    pin, salt = await request_pin_and_sd_salt(ctx, "Enter PIN")

    # Check PIN and remove salt.
    if not config.change_pin(pin_to_int(pin), pin_to_int(pin), salt, None):
        await show_pin_invalid(ctx)
        raise wire.PinInvalid("PIN invalid")

    storage.sd_salt.set_auth_key(None)

    try:
        # Clean up.
        storage.sd_salt.remove_sd_salt()
    except Exception:
        # The cleanup is not necessary for the correct functioning of
        # SD-protection. If it fails for any reason, we suppress the exception,
        # because overall SD-protection was successfully disabled.
        pass

    await show_success(ctx, ("You have successfully", "disabled SD protection."))
    return Success(message="SD card protection disabled")


async def sd_protect_refresh(ctx: wire.Context, msg: SdProtect) -> Success:
    if not storage.sd_salt.is_sd_salt_enabled():
        raise wire.ProcessError("SD card protection not enabled")

    # Confirm that user wants to proceed with the operation.
    await require_confirm_sd_protect(ctx, msg)

    # Get the current PIN and salt from the SD card.
    pin, old_salt = await request_pin_and_sd_salt(ctx, "Enter PIN")

    # Check PIN and change salt.
    new_salt, new_auth_key, new_salt_tag = _make_salt()
    await set_sd_salt(new_salt, new_salt_tag, stage=True)

    if not config.change_pin(pin_to_int(pin), pin_to_int(pin), old_salt, new_salt):
        await show_pin_invalid(ctx)
        raise wire.PinInvalid("PIN invalid")

    storage.sd_salt.set_auth_key(new_auth_key)

    try:
        # Clean up.
        storage.sd_salt.commit_sd_salt()
    except Exception:
        # If the cleanup fails, then request_sd_salt() will bring the SD card
        # into a consistent state. We suppress the exception, because overall
        # SD-protection was successfully refreshed.
        pass

    await show_success(ctx, ("You have successfully", "refreshed SD protection."))
    return Success(message="SD card protection refreshed")


def require_confirm_sd_protect(ctx: wire.Context, msg: SdProtect) -> None:
    if msg.operation == SdProtectOperationType.ENABLE:
        text = Text("SD card protection", ui.ICON_CONFIG)
        text.normal(
            "Do you really want to", "secure your device with", "SD card protection?"
        )
    elif msg.operation == SdProtectOperationType.DISABLE:
        text = Text("SD card protection", ui.ICON_CONFIG)
        text.normal(
            "Do you really want to", "remove SD card", "protection from your", "device?"
        )
    elif msg.operation == SdProtectOperationType.REFRESH:
        text = Text("SD card protection", ui.ICON_CONFIG)
        text.normal(
            "Do you really want to",
            "replace the current",
            "SD card secret with a",
            "newly generated one?",
        )
    else:
        raise wire.ProcessError("Unknown operation")

    return require_confirm(ctx, text)
