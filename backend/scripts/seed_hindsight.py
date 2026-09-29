"""Seed OpsMind's Hindsight bank with historical incident memories.

Usage (from repo root):   python -m backend.scripts.seed_hindsight [--reset]
   or (from backend/):     python -m scripts.seed_hindsight [--reset]
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import get_settings  # noqa: E402
from services import hindsight_service, incident_service  # noqa: E402


async def main(reset: bool) -> int:
    s = get_settings()
    if not s.hindsight_api_key:
        print("ERROR: HINDSIGHT_API_KEY is not set (.env at repo root or backend/).", file=sys.stderr)
        return 2
    print(f"Hindsight: {s.hindsight_base_url}  bank: {s.hindsight_bank_id}")
    try:
        ping = await hindsight_service.ping()
        print(f"  connected. bank exists: {ping['bank_exists']}")
        items = incident_service.historical_memory_items(hindsight_service.build_item)
        kinds: dict[str, int] = {}
        for it in items:
            kinds[it["metadata"]["type"]] = kinds.get(it["metadata"]["type"], 0) + 1
        print(f"  prepared {len(items)} memories: {kinds}")

        def progress(p):
            if "deleted" in p:
                print(f"  reset: deleted {p['deleted']} OpsMind documents")
            elif "submitted" in p:
                print(f"  submitted {p['submitted']}/{p['total']}")
            else:
                print(f"  processing... pending={p['pending_operations']} memories={p['total_memories']}")

        result = await hindsight_service.seed_memories(items, reset=reset, on_progress=progress)
        st = result["stats"]
        print(f"DONE. documents={st['total_documents']} memories={st['total_memories']} "
              f"observations={st['total_observations']} links={st['total_links']} failed_ops={st['failed_operations']}")
        return 0
    except hindsight_service.HindsightError as e:
        print(f"ERROR: {e.message}", file=sys.stderr)
        return 1
    finally:
        await hindsight_service.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="delete OpsMind-owned documents before seeding")
    sys.exit(asyncio.run(main(ap.parse_args().reset)))
