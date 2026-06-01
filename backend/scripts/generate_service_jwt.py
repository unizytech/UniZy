#!/usr/bin/env python3
"""
Generate Service JWT Token for Web App Client

Reads configuration from backend/.env file:
    CLIENT_ID=<uuid>
    CLIENT_NAME=<name>
    SERVICE_JWT_SECRET=<secret from api_clients.jwt_secret>
    SERVICE_JWT_EXPIRY_HOURS=<hours>

Usage:
    cd backend
    source venv/bin/activate
    python scripts/generate_service_jwt.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Load .env file from backend directory
try:
    from dotenv import load_dotenv
    # Find the backend/.env file
    script_dir = Path(__file__).resolve().parent
    backend_dir = script_dir.parent
    env_path = backend_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded .env from: {env_path}")
    else:
        print(f"Warning: .env not found at {env_path}")
except ImportError:
    print("Warning: python-dotenv not installed. Using system env vars only.")

try:
    import jwt
except ImportError:
    print("Error: PyJWT not installed. Run: pip install PyJWT")
    sys.exit(1)


def generate_service_jwt(
    client_id: str,
    jwt_secret: str,
    client_name: str = "External Web App",
    expires_in_hours: int = 720,
    scopes: list = None,
) -> dict:
    """
    Generate a Service JWT for a web_app client.

    Args:
        client_id: The API client UUID from api_clients table
        jwt_secret: The jwt_secret from api_clients table
        client_name: Display name for the client
        expires_in_hours: Token validity in hours (default: 720 = 30 days)
        scopes: Permission scopes (default: standard read/write)

    Returns:
        dict with token, expires_at, and payload
    """
    if scopes is None:
        scopes = [
            "read:extractions",
            "write:extractions",
            "read:students",
            "write:students",
            "read:templates",
            "read:counsellors",
        ]

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=expires_in_hours)

    payload = {
        "sub": client_id,
        "client_name": client_name,
        "client_type": "web_app",
        "scopes": scopes,
        "school_id": None,  # Global access
        "allowed_counsellor_ids": None,  # All counsellors
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": "1hat-api",
    }

    token = jwt.encode(payload, jwt_secret, algorithm="HS256")

    expires_in_days = expires_in_hours / 24

    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "expires_in_hours": expires_in_hours,
        "expires_in_days": round(expires_in_days, 1),
        "payload": payload,
    }


def main():
    """
    Main function - reads config from .env file and generates JWT.

    Required .env variables:
        CLIENT_ID=<uuid from api_clients table>
        CLIENT_NAME=<display name>
        SERVICE_JWT_SECRET=<jwt_secret from api_clients table>
        SERVICE_JWT_EXPIRY_HOURS=<hours, e.g. 5000>
    """
    print()

    # Read from environment (loaded from .env)
    client_id = os.getenv("CLIENT_ID", "").strip()
    client_name = os.getenv("CLIENT_NAME", "External Web App").strip()
    jwt_secret = os.getenv("SERVICE_JWT_SECRET", "").strip()
    expiry_hours_str = os.getenv("SERVICE_JWT_EXPIRY_HOURS", "720").strip()

    # Parse expiry hours
    try:
        expiry_hours = int(expiry_hours_str)
    except ValueError:
        print(f"Error: SERVICE_JWT_EXPIRY_HOURS must be a number, got: {expiry_hours_str}")
        sys.exit(1)

    # Validate required values
    errors = []

    if not client_id:
        errors.append("CLIENT_ID is missing in .env")

    if not jwt_secret:
        errors.append("SERVICE_JWT_SECRET is missing in .env")
        print("\n" + "=" * 70)
        print("TO GET YOUR SERVICE_JWT_SECRET:")
        print("=" * 70)
        print("\nRun this SQL in Supabase:")
        print("-" * 70)
        print(f"SELECT jwt_secret FROM api_clients WHERE id = '{client_id}';")
        print("-" * 70)
        print("\nThen add it to backend/.env:")
        print("SERVICE_JWT_SECRET=<the jwt_secret value>")
        print()

    if errors:
        print("\nErrors found:")
        for err in errors:
            print(f"  - {err}")
        print()
        sys.exit(1)

    # Show config
    print("Configuration from .env:")
    print(f"  CLIENT_ID:              {client_id}")
    print(f"  CLIENT_NAME:            {client_name}")
    print(f"  SERVICE_JWT_SECRET:     {'*' * 20}... (hidden)")
    print(f"  SERVICE_JWT_EXPIRY_HOURS: {expiry_hours} ({expiry_hours/24:.1f} days)")
    print()

    # Generate token
    result = generate_service_jwt(
        client_id=client_id,
        jwt_secret=jwt_secret,
        client_name=client_name,
        expires_in_hours=expiry_hours,
    )

    # Output
    print("=" * 70)
    print("SERVICE JWT TOKEN GENERATED SUCCESSFULLY")
    print("=" * 70)
    print()
    print(f"Client ID:    {client_id}")
    print(f"Client Name:  {client_name}")
    print(f"Expires:      {result['expires_at']}")
    print(f"Valid for:    {result['expires_in_hours']} hours ({result['expires_in_days']} days)")
    print()
    print("-" * 70)
    print("TOKEN (copy this):")
    print("-" * 70)
    print()
    print(result["token"])
    print()
    print("-" * 70)
    print("ADD TO YOUR WEB APP .env:")
    print("-" * 70)
    print()
    print(f'SERVICE_JWT_TOKEN={result["token"]}')
    print()
    print("-" * 70)
    print("USAGE IN YOUR WEB APP:")
    print("-" * 70)
    print()
    print("// JavaScript/TypeScript")
    print('const SERVICE_JWT = process.env.SERVICE_JWT_TOKEN;')
    print()
    print('fetch("https://your-backend.com/api/v1/counsellors", {')
    print('  headers: {')
    print('    "Authorization": `Bearer ${SERVICE_JWT}`,')
    print('    "Content-Type": "application/json"')
    print('  }')
    print('});')
    print()
    print("-" * 70)
    print("TEST COMMAND:")
    print("-" * 70)
    print()
    token_preview = result["token"][:60] + "..." if len(result["token"]) > 60 else result["token"]
    print(f'curl -X GET "http://localhost:8000/api/v1/counsellors" \\')
    print(f'  -H "Authorization: Bearer {token_preview}"')
    print()
    print("=" * 70)

    # Also save to a file for convenience
    script_dir = Path(__file__).resolve().parent
    output_file = script_dir / "service_jwt_token.txt"
    with open(output_file, "w") as f:
        f.write(f"# Service JWT Token for {client_name}\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write(f"# Expires: {result['expires_at']}\n")
        f.write(f"# Valid for: {result['expires_in_hours']} hours ({result['expires_in_days']} days)\n")
        f.write(f"# Client ID: {client_id}\n\n")
        f.write(f"SERVICE_JWT_TOKEN={result['token']}\n")

    print(f"Token also saved to: {output_file}")
    print()


if __name__ == "__main__":
    main()
