"""One-time Google sign-in. Opens the browser, asks for the read-only Gmail scope, writes token.json.

    python -m agent.auth_gmail

Needs credentials.json (an OAuth client of type "Desktop app") in the repo root. Both files are gitignored.
"""
from __future__ import annotations

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> None:
    creds_path = ROOT / "credentials.json"
    if not creds_path.exists():
        raise SystemExit("credentials.json not found in the repo root (download it from Google Cloud, OAuth client, Desktop app)")
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    (ROOT / "token.json").write_text(creds.to_json(), encoding="utf-8")
    print("token.json written. Scope granted:", " ".join(creds.scopes or []))


if __name__ == "__main__":
    main()
