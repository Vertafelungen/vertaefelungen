#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alttext-Automatisierung (Credentials-Loader)
Version: 2025-03-10 12:00 Europe/Berlin

Dieses Skript demonstriert die sichere Credential-Ladung für Google APIs.
Es nimmt keine API-Aufrufe vor, sondern validiert nur die Auth-Konfiguration.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from google.oauth2 import service_account


def load_google_credentials():
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        path = Path(creds_path)
        if path.exists():
            return (
                service_account.Credentials.from_service_account_file(str(path)),
                "file",
            )
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS ist gesetzt, aber die Datei existiert nicht."
        )

    json_env = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if json_env:
        data = json.loads(json_env)
        return (
            service_account.Credentials.from_service_account_info(data),
            "env",
        )

    raise RuntimeError(
        "Fehlende Credentials: Setze GOOGLE_APPLICATION_CREDENTIALS (Pfad) oder "
        "GOOGLE_SERVICE_ACCOUNT_JSON (JSON-Inhalt)."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Alttext-Automatisierung Credentials Check")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Placeholder für echte API-Aufrufe (standardmäßig wird nur validiert).",
    )
    args = parser.parse_args()

    try:
        _creds, source = load_google_credentials()
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    print(f"Credentials geladen (Quelle: {source}).")
    if not args.execute:
        print("Dry-Run: Keine API-Aufrufe ausgeführt.")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
