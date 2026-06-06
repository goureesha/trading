"""
Fyers API Authentication Module
================================
Handles OAuth2 login flow and token caching for Fyers API v3.
Run this script once daily to generate a fresh access token.

Usage:
    python fyers_auth.py          # Opens browser for login
    python fyers_auth.py --token  # Show current cached token
"""

import os
import sys
import json
import hashlib
import webbrowser
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

# ── Configuration ──
CLIENT_ID = "70OO9494R9-100"
SECRET_KEY = "M4RUQHA4T0"
REDIRECT_URI = "https://127.0.0.1"
RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"
STATE = "tradesignalpro"

TOKEN_FILE = Path(__file__).parent / ".fyers_token.json"


def get_auth_url():
    """Generate the Fyers login URL."""
    from fyers_apiv3 import fyersModel
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type=RESPONSE_TYPE,
        grant_type=GRANT_TYPE,
        state=STATE,
    )
    return session.generate_authcode()


def generate_token(auth_code):
    """Exchange auth code for access token."""
    from fyers_apiv3 import fyersModel
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type=RESPONSE_TYPE,
        grant_type=GRANT_TYPE,
    )
    session.set_token(auth_code)
    response = session.generate_token()

    if response.get("s") == "ok" or "access_token" in response:
        token_data = {
            "access_token": response["access_token"],
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=23)).isoformat(),
            "client_id": CLIENT_ID,
        }
        TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
        print(f"✅ Token saved to {TOKEN_FILE}")
        print(f"   Valid until: {token_data['expires_at']}")
        return response["access_token"]
    else:
        print(f"❌ Token generation failed: {response}")
        return None


def load_token():
    """Load cached token if still valid."""
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        expires = datetime.fromisoformat(data["expires_at"])
        if datetime.now() < expires:
            return data["access_token"]
        else:
            print("⚠️  Token expired. Run: python fyers_auth.py")
            return None
    except Exception:
        return None


def get_fyers_client():
    """Get an authenticated Fyers API client."""
    from fyers_apiv3 import fyersModel
    token = load_token()
    if not token:
        return None
    fyers = fyersModel.FyersModel(
        client_id=CLIENT_ID,
        is_async=False,
        token=token,
        log_path=str(Path(__file__).parent / "fyers_logs"),
    )
    return fyers


def interactive_login():
    """Run the full interactive login flow."""
    print("=" * 50)
    print("  Fyers API Login")
    print("=" * 50)

    # Check if token already valid
    token = load_token()
    if token:
        print(f"✅ Token already valid!")
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        print(f"   Expires: {data['expires_at']}")
        return token

    # Generate login URL
    auth_url = get_auth_url()
    print(f"\n📌 Opening browser for Fyers login...")
    print(f"   URL: {auth_url}\n")
    webbrowser.open(auth_url)

    print("After logging in, you'll be redirected to a URL like:")
    print("  https://127.0.0.1/?s=ok&code=XXXXX&state=...")
    print("\nPaste the FULL redirect URL here:")

    redirect_url = input("\n> ").strip()

    # Extract auth code from URL
    try:
        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)
        auth_code = params.get("auth_code", params.get("code", [None]))[0]
        if not auth_code:
            print("❌ Could not find auth_code in URL")
            return None
    except Exception as e:
        print(f"❌ Error parsing URL: {e}")
        return None

    return generate_token(auth_code)


if __name__ == "__main__":
    if "--token" in sys.argv:
        token = load_token()
        if token:
            data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            print(f"Token: {token[:20]}...")
            print(f"Expires: {data['expires_at']}")
        else:
            print("No valid token. Run: python fyers_auth.py")
    else:
        interactive_login()
