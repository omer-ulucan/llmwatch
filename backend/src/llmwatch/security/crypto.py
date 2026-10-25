"""
Module: crypto.py
Purpose: Encrypts provider API keys at rest and masks them for display.
WHY: Provider keys are bearer credentials worth real money. They are stored as Fernet
tokens (key derived from the server secret), decrypted only when calling the
provider, and never sent back to the browser; the UI gets a short hint instead.
"""

from cryptography.fernet import Fernet, InvalidToken

from llmwatch.security.secrets import fernet_key


class SecretDecryptionError(Exception):
    """The stored secret can't be decrypted (usually: the server secret changed)."""


def encrypt_secret(plaintext: str) -> str:
    return Fernet(fernet_key()).encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return Fernet(fernet_key()).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise SecretDecryptionError(
            "Stored API key can't be decrypted; the server secret probably changed. "
            "Re-enter the key."
        ) from exc


def secret_hint(plaintext: str) -> str:
    """The last 4 characters, or nothing for very short secrets."""
    return plaintext[-4:] if len(plaintext) >= 12 else ""


def mask_secret(hint: str | None) -> str:
    """Display form, e.g. "••••abcd"."""
    return f"••••{hint}" if hint else "••••"
