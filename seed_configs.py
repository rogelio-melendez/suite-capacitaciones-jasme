# -*- coding: utf-8 -*-
"""Run this ONCE, locally, after creating your Supabase project and its
`exam_configs` table, to copy the two exam keys you already had
(config/nom_004.json, config/nom_026.json) into Supabase -- so you don't
have to retype them by hand in the app.

Usage (from a terminal, inside the jasme_app folder):
    pip install supabase
    python seed_configs.py <SUPABASE_URL> <SUPABASE_SERVICE_ROLE_KEY>

Both values come from your Supabase project's Settings -> API page.
"""
import json
import sys
from pathlib import Path

from supabase import create_client

CONFIG_DIR = Path(__file__).parent / "config"


def main():
    if len(sys.argv) != 3:
        print("Uso: python seed_configs.py <SUPABASE_URL> <SUPABASE_SERVICE_ROLE_KEY>")
        sys.exit(1)

    url, key = sys.argv[1], sys.argv[2]
    client = create_client(url, key)

    json_files = list(CONFIG_DIR.glob("*.json"))
    if not json_files:
        print("No se encontraron archivos .json en config/ -- nada que migrar.")
        return

    for path in json_files:
        config = json.loads(path.read_text(encoding="utf-8"))
        client.table("exam_configs").upsert(config, on_conflict="nom_id").execute()
        print(f"Migrado: {config['title']}")

    print(f"\nListo -- {len(json_files)} clave(s) de examen copiadas a Supabase.")


if __name__ == "__main__":
    main()
