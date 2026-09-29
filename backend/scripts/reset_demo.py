"""Reset the demo: clear local state and delete engineer-feedback memories created by OpsMind.

Usage: python -m backend.scripts.reset_demo [--reseed]
Only documents with OpsMind's feedback-/lesson- prefixes are deleted; nothing else in the bank is touched.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import hindsight_service, incident_service  # noqa: E402


async def main(reseed: bool) -> int:
    try:
        incident_service.reset_state()
        ids = await hindsight_service.list_document_ids(hindsight_service.LEARNED_PREFIXES)
        n = await hindsight_service.delete_documents(ids)
        print(f"Local demo state cleared. Deleted {n} learned memories: {ids}")
        if reseed:
            items = incident_service.historical_memory_items(hindsight_service.build_item)
            r = await hindsight_service.seed_memories(items)
            print(f"Re-seeded {r['documents_submitted']} documents.")
        return 0
    except hindsight_service.HindsightError as e:
        print(f"ERROR: {e.message}", file=sys.stderr)
        return 1
    finally:
        await hindsight_service.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reseed", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args().reseed)))
