from cryptography.fernet import Fernet


def encrypt(secret_key: str, plaintext: str) -> str:
    return Fernet(secret_key.encode()).encrypt(plaintext.encode()).decode()


def decrypt(secret_key: str, ciphertext: str) -> str:
    return Fernet(secret_key.encode()).decrypt(ciphertext.encode()).decode()
