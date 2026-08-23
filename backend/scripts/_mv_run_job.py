"""One-off driver: re-run lost background jobs in-process.

Usage:
  python scripts/_mv_run_job.py ingest <presentation_public_id>
  python scripts/_mv_run_job.py generate <lesson_public_id>
"""
import asyncio
import sys


async def do_ingest(public_id: str) -> None:
    from app.workers.tasks import _start_source_ingestion_async

    result = await _start_source_ingestion_async(public_id)
    print("INGEST DONE", public_id, "->", result)


async def do_generate(lesson_public_id: str) -> None:
    from app.database.unit_of_work import UnitOfWork
    from app.services.lesson_generation_service import LessonGenerationService

    async with UnitOfWork() as uow:
        await LessonGenerationService(uow).run_generation(lesson_public_id)
    print("GENERATE DONE", lesson_public_id)


async def main() -> None:
    action, public_id = sys.argv[1], sys.argv[2]
    if action == "ingest":
        await do_ingest(public_id)
    elif action == "generate":
        await do_generate(public_id)
    else:
        raise SystemExit(f"unknown action {action}")


if __name__ == "__main__":
    asyncio.run(main())
