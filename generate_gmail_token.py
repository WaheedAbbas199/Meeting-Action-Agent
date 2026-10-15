
import http.server
import urllib.parse
import webbrowser
import requests
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
REDIRECT_URI = "http://localhost:8765/"
SCOPES = "https://www.googleapis.com/auth/gmail.send"

client_id = input("Google OAuth Client ID: ").strip()
client_secret = input("Google OAuth Client Secret: ").strip()
state = secrets.token_urlsafe(24)

params = {
    "client_id": client_id,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": SCOPES,
    "access_type": "offline",
    "prompt": "consent",
    "state": state,
}

auth_url = (
    "https://accounts.google.com/o/oauth2/v2/auth?"
    + urllib.parse.urlencode(params)
)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.parse_qs(
            urllib.parse.urlparse(self.path).query
        )

        if query.get("state", [""])[0] != state:
            self.respond(400, "Invalid state. Close this tab.")
            return

        if query.get("error"):
            self.respond(400, "Google authorization was cancelled.")
            return

        code = query.get("code", [None])[0]
        if not code:
            self.respond(400, "Authorization code missing.")
            return

        try:
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=30,
            )
            result = response.json()
            response.raise_for_status()
        except Exception:
            print("Google token exchange failed. Check OAuth settings.")
            self.respond(400, "Token exchange failed. Check terminal.")
            return

        refresh_token = result.get("refresh_token")
        if not refresh_token:
            print("Google did not return a refresh token.")
            print("Try checking OAuth consent-screen settings.")
            self.respond(400, "No refresh token returned. Check terminal.")
            return

        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
        lines = [
            line for line in lines
            if not line.startswith("GMAIL_REFRESH_TOKEN=")
        ]
        lines.append(f"GMAIL_REFRESH_TOKEN={refresh_token}")
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

        print("SUCCESS: Gmail refresh token saved in Meeting Action Agent .env")
        self.respond(200, "Authorization successful. You can close this tab.")

    def respond(self, status, message):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))

    def log_message(self, *args):
        pass

server = http.server.HTTPServer(("localhost", 8765), Handler)
print("Opening Google authorization in your browser...")
webbrowser.open(auth_url)
print("Complete authorization in the browser.")
server.handle_request()
server.server_close()
