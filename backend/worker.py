"""Standalone document processing worker."""
import asyncio, sys
sys.path.insert(0, '/app')
from app.config.settings import settings
from app.di.container import DIContainer

async def worker_main():
    container = DIContainer(settings)
    await container.init_async()
    while True:
        try:
            task = await container.task_queue.dequeue(timeout=5.0)
            if task:
                await container.doc_use_case.process_document(task.doc_id)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(1)
    await container.close_async()

if __name__ == "__main__":
    asyncio.run(worker_main())
