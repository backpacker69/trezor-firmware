from micropython import const

import storage.device
from storage import common
from trezor import io
from trezor.crypto import hmac
from trezor.crypto.hashlib import sha256
from trezor.utils import consteq

if False:
    from typing import Optional
    from typing_extensions import Literal

# Namespace:
_NAMESPACE = common.APP_SD_SALT

# Keys:
_SD_SALT_AUTH_KEY = const(0x00)  # bytes


SD_CARD_HOT_SWAPPABLE = False
SD_SALT_LEN_BYTES = const(32)
SD_SALT_AUTH_TAG_LEN_BYTES = const(16)
SD_SALT_AUTH_KEY_LEN_BYTES = const(16)


class SdSaltError(Exception):
    READ_FAILED = 0  # type: Literal[0]
    WRITE_FAILED = 1  # type: Literal[1]
    CARD_MISMATCH = 2  # type: Literal[2]

    def __init__(self, code: Literal[0, 1, 2]) -> None:
        self.code = code
        super().__init__()


def get_auth_key() -> Optional[bytes]:
    """
    The key used to check the authenticity of the SD card salt.
    """
    auth_key = common.get(_NAMESPACE, _SD_SALT_AUTH_KEY, public=True)
    if auth_key is not None and len(auth_key) != SD_SALT_AUTH_KEY_LEN_BYTES:
        raise ValueError
    return auth_key


def set_auth_key(auth_key: Optional[bytes]) -> None:
    """
    The key used to check the authenticity of the SD card salt.
    """
    from storage.sd_salt import SD_SALT_AUTH_KEY_LEN_BYTES

    if auth_key is not None:
        if len(auth_key) != SD_SALT_AUTH_KEY_LEN_BYTES:
            raise ValueError
        return common.set(_NAMESPACE, _SD_SALT_AUTH_KEY, auth_key, public=True)
    else:
        return common.delete(_NAMESPACE, _SD_SALT_AUTH_KEY, public=True)


def is_sd_salt_enabled() -> bool:
    return get_auth_key() is not None


def compute_auth_tag(salt: bytes, auth_key: bytes) -> bytes:
    digest = hmac.new(auth_key, salt, sha256).digest()
    return digest[:SD_SALT_AUTH_TAG_LEN_BYTES]


def _get_device_dir() -> str:
    return "/trezor/device_{}".format(storage.device.get_device_id().lower())


def _get_salt_path(new: bool = False) -> str:
    return "{}/salt{}".format(_get_device_dir(), ".new" if new else "")


def _load_salt(fs: io.FatFS, auth_key: bytes, path: str) -> Optional[bytearray]:
    # Load the salt file if it exists.
    try:
        with fs.open(path, "r") as f:
            salt = bytearray(SD_SALT_LEN_BYTES)
            stored_tag = bytearray(SD_SALT_AUTH_TAG_LEN_BYTES)
            f.read(salt)
            f.read(stored_tag)
    except OSError:
        return None

    # Check the salt's authentication tag.
    computed_tag = compute_auth_tag(salt, auth_key)
    if not consteq(computed_tag, stored_tag):
        return None

    return salt


def load_sd_salt() -> Optional[bytearray]:
    salt_auth_key = get_auth_key()
    if salt_auth_key is None:
        return None

    sd = io.SDCard()
    if not sd.power(True):
        raise OSError

    salt_path = _get_salt_path()
    new_salt_path = _get_salt_path(new=True)

    try:
        fs = io.FatFS()
        fs.mount()
        salt = _load_salt(fs, salt_auth_key, salt_path)
        if salt is not None:
            return salt

        # Check if there is a new salt.
        salt = _load_salt(fs, salt_auth_key, new_salt_path)
        if salt is None:
            # No valid salt file on this SD card.
            raise SdSaltError(SdSaltError.CARD_MISMATCH)

        # Normal salt file does not exist, but new salt file exists. That means that
        # SD salt regeneration was interrupted earlier. Bring into consistent state.
        # TODO Possibly overwrite salt file with random data.
        try:
            fs.unlink(salt_path)
        except OSError:
            pass

        try:
            fs.rename(new_salt_path, salt_path)
        except OSError as e:
            raise SdSaltError(SdSaltError.WRITE_FAILED) from e

        return salt
    finally:
        fs.unmount()
        sd.power(False)


def set_sd_salt(salt: bytes, salt_tag: bytes, stage: bool = False) -> None:
    salt_path = _get_salt_path(stage)
    sd = io.SDCard()
    if not sd.power(True):
        raise OSError

    try:
        fs = io.FatFS()
        fs.mount()
        fs.mkdir("/trezor", True)
        fs.mkdir(_get_device_dir(), True)
        with fs.open(salt_path, "w") as f:
            f.write(salt)
            f.write(salt_tag)
    finally:
        fs.unmount()
        sd.power(False)


def commit_sd_salt() -> None:
    salt_path = _get_salt_path(new=False)
    new_salt_path = _get_salt_path(new=True)

    sd = io.SDCard()
    fs = io.FatFS()
    if not sd.power(True):
        raise OSError

    try:
        fs.mount()
        # TODO Possibly overwrite salt file with random data.
        try:
            fs.unlink(salt_path)
        except OSError:
            pass
        fs.rename(new_salt_path, salt_path)
    finally:
        fs.unmount()
        sd.power(False)


def remove_sd_salt() -> None:
    salt_path = _get_salt_path()

    sd = io.SDCard()
    fs = io.FatFS()
    if not sd.power(True):
        raise OSError

    try:
        fs.mount()
        # TODO Possibly overwrite salt file with random data.
        fs.unlink(salt_path)
    finally:
        fs.unmount()
        sd.power(False)
