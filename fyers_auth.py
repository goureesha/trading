"""
Fyers Auto-Login — Fully Automatic Token Generation
=====================================================
Uses REST API for programmatic login with PIN + TOTP.
Falls back to manual browser login if auto-login fails.

Usage:
    python fyers_auth.py              # Auto-login
    python fyers_auth.py --token      # Show token status
    python fyers_auth.py --manual     # Manual browser login
"""

import hashlib
import hmac as hmac_mod
import json
import os
import struct
import sys
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

# -- Configuration --
CLIENT_ID = "70OO9494R9-100"
SECRET_KEY = "M4RUQHA4T0"
REDIRECT_URI = "https://127.0.0.1"
FYERS_ID = "YG02745"
FYERS_PIN = "1122"
TOTP_SECRET = "HD6TIW5P3RGSUYSSSSMERQV3LOCPHQ5HR"

TOKEN_FILE = Path(__file__).parent / ".fyers_token.json"
TOKEN_URL = "https://api-t1.fyers.in/api/v3/validate-authcode"

if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def _b32_decode(s):
    s = s.upper().rstrip("=")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    bits = ""
    for c in s:
        bits += format(alphabet.index(c), '05b')
    num_bytes = len(bits) // 8
    return bytes(int(bits[i*8:(i+1)*8], 2) for i in range(num_bytes))


def generate_totp():
    key = _b32_decode(TOTP_SECRET)
    counter = int(time.time()) // 30
    counter_bytes = struct.pack(">Q", counter)
    h = hmac_mod.new(key, counter_bytes, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF
    return str(code % 1000000).zfill(6)


def _app_id_hash():
    return hashlib.sha256(f"{CLIENT_ID}:{SECRET_KEY}".encode()).hexdigest()


def auto_login():
    """Auto-login to Fyers using REST API."""
    print("  [*] Auto-login to Fyers...")

    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })

    # Step 1: Send login OTP
    try:
        r = s.post("https://api-t2.fyers.in/vagator/v2/send_login_otp_v2", json={
            "fy_id": FYERS_ID,
            "app_id": "2",
        })
        d = r.json()
        rk = d.get("request_key")
        if not rk:
            # Try alternate endpoint
            r = s.post("https://api-t2.fyers.in/vagator/v2/send_login_otp", json={
                "fy_id": FYERS_ID,
                "app_id": "2",
            })
            d = r.json()
            rk = d.get("request_key")
        if not rk:
            print(f"  [!] Login init failed: {d}")
            print("  [*] Trying manual login flow...")
            return manual_login()
        print("  [+] Login initiated")
    except Exception as e:
        print(f"  [!] Login error: {e}")
        return manual_login()

    # Step 2: Verify PIN
    try:
        pin_hash = hashlib.sha256(f"{FYERS_PIN}".encode()).hexdigest()
        r = s.post("https://api-t2.fyers.in/vagator/v2/verify_pin_v2", json={
            "request_key": rk,
            "identity": pin_hash,
        })
        d = r.json()
        rk2 = d.get("request_key")
        if not rk2:
            # Try with raw PIN
            r = s.post("https://api-t2.fyers.in/vagator/v2/verify_pin", json={
                "request_key": rk,
                "identity": FYERS_PIN,
            })
            d = r.json()
            rk2 = d.get("request_key")
        if not rk2:
            # Try alternate format
            r = s.post("https://api-t2.fyers.in/vagator/v2/verify_pin_v2", json={
                "request_key": rk,
                "identity": FYERS_PIN,
            })
            d = r.json()
            rk2 = d.get("request_key")
        if not rk2:
            print(f"  [!] PIN failed: {d}")
            return manual_login()
        rk = rk2
        print("  [+] PIN verified")
    except Exception as e:
        print(f"  [!] PIN error: {e}")
        return manual_login()

    # Step 3: Verify TOTP
    try:
        totp = generate_totp()
        r = s.post("https://api-t2.fyers.in/vagator/v2/verify_otp", json={
            "request_key": rk,
            "otp": totp,
        })
        d = r.json()
        rk2 = d.get("request_key")
        if not rk2:
            print(f"  [!] TOTP failed: {d}")
            return manual_login()
        rk = rk2
        print(f"  [+] TOTP verified")
    except Exception as e:
        print(f"  [!] TOTP error: {e}")
        return manual_login()

    # Step 4: Get auth code
    try:
        r = s.post("https://api-t2.fyers.in/vagator/v2/token", json={
            "fyers_id": FYERS_ID,
            "app_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "appType": "100",
            "code_challenge": "",
            "state": "tradesignalpro",
            "scope": "",
            "nonce": "",
            "response_type": "code",
            "create_cookie": True,
        }, headers={"authorization": f"Bearer {rk}"})

        d = r.json()
        url = d.get("Url") or d.get("url", "")
        if not url:
            print(f"  [!] Auth code failed: {d}")
            return manual_login()

        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        auth_code = params.get("auth_code", params.get("code", [None]))[0]
        if not auth_code:
            print(f"  [!] No auth_code in URL")
            return manual_login()
        print("  [+] Auth code obtained")
    except Exception as e:
        print(f"  [!] Auth code error: {e}")
        return manual_login()

    # Step 5: Exchange for token
    return _exchange_token(auth_code)


def _exchange_token(auth_code):
    """Exchange auth code for access token."""
    try:
        r = requests.post(TOKEN_URL, json={
            "grant_type": "authorization_code",
            "appIdHash": _app_id_hash(),
            "code": auth_code,
        })
        d = r.json()
        if "access_token" in d:
            _save_token(d["access_token"])
            return d["access_token"]
        print(f"  [!] Token exchange failed: {d}")
        return None
    except Exception as e:
        print(f"  [!] Token error: {e}")
        return None


def _save_token(token):
    """Save token to file."""
    data = {
        "access_token": token,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=23)).isoformat(),
        "client_id": CLIENT_ID,
    }
    TOKEN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  [OK] Token saved! Valid until {data['expires_at']}")


def load_token():
    """Load cached token if valid."""
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        expires = datetime.fromisoformat(data["expires_at"])
        if datetime.now() < expires:
            return data["access_token"]
        return None
    except Exception:
        return None


def ensure_token():
    """Get valid token - cached or fresh."""
    token = load_token()
    if token:
        return token
    return auto_login()


def manual_login():
    """Browser-based login as fallback."""
    print("\n  === Manual Login ===")
    auth_url = (
        f"https://api-t1.fyers.in/api/v3/generate-authcode"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code&state=tradesignalpro"
    )
    print(f"  Opening browser...")
    webbrowser.open(auth_url)
    print("  After login, paste the FULL redirect URL:")

    redirect_url = input("\n  > ").strip()
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    auth_code = params.get("auth_code", params.get("code", [None]))[0]

    if not auth_code:
        print("  [!] No auth_code found")
        return None

    return _exchange_token(auth_code)


if __name__ == "__main__":
    print()
    if "--token" in sys.argv:
        token = load_token()
        if token:
            data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            print(f"  Token: {token[:20]}...")
            print(f"  Expires: {data['expires_at']}")
        else:
            print("  No valid token. Run: python fyers_auth.py")
    elif "--manual" in sys.argv:
        manual_login()
    else:
        token = load_token()
        if token:
            data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            print(f"  [OK] Token already valid!")
            print(f"  Expires: {data['expires_at']}")
        else:
            auto_login()
    print()
