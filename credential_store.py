import os

from dotenv import dotenv_values
import keyring

try:
    keyring.get_keyring()
except keyring.errors.NoKeyringError:
    try:
        from keyrings.alt.file import EncryptedKeyring
        keyring.set_keyring(EncryptedKeyring())
    except Exception:
        from keyrings.alt.file import PlaintextKeyring
        keyring.set_keyring(PlaintextKeyring())

SERVICE_NAME = "nh-ipa"
KEY_NAMES = ("NH_APP_KEY", "NH_APP_SECRET")


def _load_from_env():
    loaded = {}
    for key_name in KEY_NAMES:
        value = os.getenv(key_name)
        if value:
            loaded[key_name] = value
    if loaded:
        return loaded

    env_values = dotenv_values(".env") or {}
    return {key: env_values.get(key) for key in KEY_NAMES if env_values.get(key)}


def save_credentials_from_env():
    env_values = _load_from_env()
    saved = []

    for key_name in KEY_NAMES:
        value = env_values.get(key_name)
        if value:
            keyring.set_password(SERVICE_NAME, key_name, value)
            saved.append(key_name)

    return saved


def get_credentials():
    loaded = {}

    for key_name in KEY_NAMES:
        value = os.getenv(key_name)
        if value:
            loaded[key_name] = value
            keyring.set_password(SERVICE_NAME, key_name, value)
            continue

        value = keyring.get_password(SERVICE_NAME, key_name)
        if value is None:
            value = _load_from_env().get(key_name)
            if value:
                keyring.set_password(SERVICE_NAME, key_name, value)

        if value:
            loaded[key_name] = value

    missing = [key for key in KEY_NAMES if not loaded.get(key)]
    if missing:
        raise RuntimeError(
            "NH_APP_KEY와 NH_APP_SECRET을 환경 변수, 안전 저장소 또는 .env에서 확인할 수 없습니다."
        )

    return loaded["NH_APP_KEY"], loaded["NH_APP_SECRET"]
