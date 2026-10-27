"""Personal Intervals.icu key: environment or native OS credential storage."""

import os
import sys

SERVICE = "VitalDock/Intervals.icu"
USERNAME = "API_KEY"


def _backend():
    try:
        if sys.platform == "win32":
            from keyring.backends.Windows import WinVaultKeyring
            return WinVaultKeyring()
        if sys.platform == "darwin":
            from keyring.backends.macOS import Keyring
            return Keyring()
        import keyring
        backend = keyring.get_keyring()
        if not type(backend).__module__.startswith(("keyring.backends.SecretService",
                                                   "keyring.backends.kwallet",
                                                   "keyring.backends.libsecret")):
            raise ValueError("native credential store unavailable; use process environment instead")
        return backend
    except ImportError:
        raise ValueError('install credential storage with: pip install -e ".[live]"') from None


def load_key():
    key = os.environ.get("VITALDOCK_INTERVALS_API_KEY")
    if key:
        return _validate(key)
    try:
        key = _backend().get_password(SERVICE, USERNAME)
    except Exception:
        raise ValueError("credential_unavailable: run connect-intervals locally or set "
                         "VITALDOCK_INTERVALS_API_KEY in the server process") from None
    if not key:
        raise ValueError("credential_not_configured: run connect-intervals locally")
    return _validate(key)


def save_key(key):
    key = _validate(key)
    try:
        _backend().set_password(SERVICE, USERNAME, key)
    except Exception:
        raise ValueError("credential_store_failed: key was not saved; use process environment") from None


def _validate(key):
    if not isinstance(key, str) or not 8 <= len(key) <= 512 or any(c.isspace() for c in key):
        raise ValueError("invalid API key format")
    return key
