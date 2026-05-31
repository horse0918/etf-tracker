#!/usr/bin/env python3
"""
Run this ONCE locally to generate Gmail OAuth tokens for GitHub Actions.

Prerequisites:
  pip install google-auth-oauthlib

Steps:
  1. Go to https://console.cloud.google.com/
  2. Create a project (or use an existing one)
  3. Enable the Gmail API
  4. Go to APIs & Services > Credentials > Create Credentials > OAuth 2.0 Client ID
  5. Application type: Desktop app
  6. Download the JSON and save it as credentials.json next to this script
  7. Run: python setup_gmail_token.py
  8. A browser window will open — sign in and grant read-only Gmail access
  9. Copy the printed values into GitHub Secrets
"""
import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main():
    if not os.path.exists("credentials.json"):
        print("ERROR: credentials.json not found.")
        print("Download it from Google Cloud Console and place it here.")
        print("See the docstring at the top of this file for full instructions.")
        return

    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    with open("credentials.json") as f:
        creds_data = json.load(f)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    separator = "=" * 60
    print(f"\n{separator}")
    print("ADD THESE AS GITHUB REPOSITORY SECRETS")
    print("(Settings > Secrets and variables > Actions > New repository secret)")
    print(separator)
    print("\nSecret name:  GMAIL_CREDENTIALS")
    print("Secret value:")
    print(json.dumps(creds_data))
    print("\nSecret name:  GMAIL_TOKEN")
    print("Secret value:")
    print(json.dumps(token_data))
    print(f"\n{separator}")
    print("Also make sure NOTION_TOKEN and ANTHROPIC_API_KEY are set as secrets.")
    print(separator)


if __name__ == "__main__":
    main()
