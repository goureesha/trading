import hmac
import hashlib
import struct
import time
import base64

secret = "HD6TIW5P3RGSUYSSSSMERQV3LOCPHQ5HR"

# Decode base32 manually (lenient - handles any padding)
def b32_decode_lenient(s):
    s = s.upper().rstrip("=")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    bits = ""
    for c in s:
        idx = alphabet.index(c)
        bits += format(idx, '05b')
    # Truncate to whole bytes
    num_bytes = len(bits) // 8
    result = bytes(int(bits[i*8:(i+1)*8], 2) for i in range(num_bytes))
    return result

# Generate TOTP
def generate_totp(secret_str, digits=6, interval=30):
    key = b32_decode_lenient(secret_str)
    counter = int(time.time()) // interval
    counter_bytes = struct.pack(">Q", counter)
    h = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)

code = generate_totp(secret)
remaining = 30 - (int(time.time()) % 30)
print(f"TOTP code: {code}")
print(f"Valid for {remaining} more seconds")
print(f"Enter this in the Fyers TOTP field NOW!")
