import os
import secrets

# Best (using os.urandom):
secret_key = os.urandom(24).hex()

# Alternative (using secrets):
# secret_key = secrets.token_hex(24)

print(secret_key)