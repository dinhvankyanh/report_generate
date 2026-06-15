"""
Gmail Authentication Script
Run this once to authenticate with Gmail API
"""
from src.data_sources.gmail_service import create_gmail_service
import time

print("="*50)
print("GMAIL AUTHENTICATION")
print("="*50)
print()
print("A browser window will open.")
print("Please sign in to your Google account and allow access.")
print()

# Try to authenticate
service = create_gmail_service()
if service.authenticate():
    print()
    print("="*50)
    print("[OK] Gmail authentication successful!")
    print("    Token saved for future use.")
    print("="*50)
else:
    print()
    print("="*50)
    print("[ERROR] Authentication failed!")
    print("    Please check your credentials.json file.")
    print("="*50)