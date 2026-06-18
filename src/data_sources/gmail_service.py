"""
Gmail Service - OAuth2 authentication and email fetching
"""
from typing import List, Dict, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .. import config


class GmailService:
    """Service to fetch emails from Gmail using OAuth2"""

    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

    def __init__(self):
        # Credentials live with the code, not the (selectable) data folder
        self.token_file = config.GMAIL_TOKEN_FILE
        self.credentials_file = config.CREDENTIALS_FILE
        self.service = None

    def authenticate(self) -> bool:
        """
        Authenticate with Gmail using OAuth2
        Returns True if successful, False otherwise
        """
        creds = None

        # Load existing token
        if self.token_file.exists():
            try:
                token_data = self._load_token()
                if token_data:
                    creds = Credentials.from_authorized_user_info(token_data, self.SCOPES)
            except Exception as e:
                print(f"[INFO] Could not load existing token: {e}")
                creds = None

        # If no valid credentials, run OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    from google.auth.transport.requests import Request
                    creds.refresh(Request())
                    self._save_token(creds)
                    print("[OK] Gmail token refreshed!")
                    return self._build_service(creds)
                except Exception as e:
                    print(f"[INFO] Token refresh failed: {e}")

            # Need to run OAuth flow
            if not self.credentials_file.exists():
                print("[WARNING] credentials.json not found!")
                print("   Please download from Google Cloud Console:")
                print("   1. Go to https://console.cloud.google.com")
                print("   2. Create OAuth 2.0 credentials (Desktop App)")
                print("   3. Download as credentials.json and place in project root")
                return False

            try:
                print("[INFO] Starting Gmail OAuth flow...")
                print("[INFO] A browser window will open. Please sign in and allow access.")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), self.SCOPES
                )
                creds = flow.run_local_server(port=0)

                # Save for future use
                self._save_token(creds)
                print("[OK] Gmail authentication successful!")
            except Exception as e:
                print(f"[WARNING] Gmail auth failed: {e}")
                return False

        # Build Gmail service
        return self._build_service(creds)

    def _build_service(self, creds: Credentials) -> bool:
        """Build Gmail service with credentials"""
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            return True
        except Exception as e:
            print(f"[WARNING] Could not build Gmail service: {e}")
            return False

    def _save_token(self, creds: Credentials):
        """Save token to file using pickle for proper serialization"""
        import pickle

        token_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': list(creds.scopes) if creds.scopes else self.SCOPES
        }

        with open(self.token_file, 'wb') as f:
            pickle.dump(token_data, f)

    def _load_token(self) -> dict:
        """Load token from file"""
        import pickle

        if not self.token_file.exists():
            return {}

        with open(self.token_file, 'rb') as f:
            return pickle.load(f)

    def search_emails(self, query: str, max_results: int = 50) -> List[Dict]:
        """Search emails with given query"""
        if not self.service:
            return []

        try:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()

            messages = results.get('messages', [])
            emails = []

            for msg in messages:
                email_data = self._get_email(msg['id'])
                if email_data:
                    emails.append(email_data)

            return emails

        except HttpError as e:
            print(f"[WARNING] Gmail API error: {e}")
            return []

    def _get_email(self, message_id: str) -> Optional[Dict]:
        """Get full email content by ID"""
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            # Extract headers
            headers = message.get('payload', {}).get('headers', {})
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')

            # Get body
            body = self._extract_body(message.get('payload', {}))

            return {
                'id': message_id,
                'subject': subject,
                'sender': sender,
                'date': date,
                'body': body
            }

        except Exception:
            return None

    def _extract_body(self, payload: dict) -> str:
        """Extract email body from payload"""
        # Try to get from parts
        parts = payload.get('parts', [])
        if parts:
            for part in parts:
                if part.get('mimeType') == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        return self._decode_base64(data)

        # Try direct body
        body = payload.get('body', {}).get('data', '')
        if body:
            return self._decode_base64(body)

        return ''

    def _decode_base64(self, data: str) -> str:
        """Decode base64 encoded string"""
        import base64
        try:
            return base64.urlsafe_b64decode(data).decode('utf-8')
        except Exception:
            return data


def create_gmail_service() -> GmailService:
    """Factory function to create Gmail service"""
    return GmailService()