#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSOT -> Markdown Generator (deterministic)
Version: ssot_generator/2025-10-13T12:35:00+02:00

Repo layout target: wissen/content/{de|en}/.../<slug>/index.md

- Liest CSV aus:
    1) SSOT_CSV_PATH (lokal) ODER
    2) GSHEET_CSV_URL (kanonisch) ODER
    3) GSHEET_SHEET_ID + GSHEET_GID (baut Export-URL selbst)
- Normalisiert Text (UTF-8, NFC, entfernt ZWSP/NBSP, ersetzt Smart Quotes, Dashes, Ellipsis)
- Mappt DE/EN aus EINER CSV-Zeile auf je eine Markdown-Datei (index.md)
- YAML: strikt mit ---/---, UTF-8 LF, korrekt gequotet, stabile Feldreihenfolge
- Datentypen: price_cents:int, in_stock:bool, Listen korrekt, Variants normalisiert
- Entfernt "public" aus Pfaden, schreibt nur wenn Content sich geändert hat (idempotent)
- Pruning: entfernt verwaiste, vom Generator verwaltete Seiten (managed_by-Stempel)
"""

from __future__ import annotations

import os
import sys
import re
import io
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

import unicodedata
from unidecode import uni
