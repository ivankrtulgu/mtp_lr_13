import asyncio
import logging
import sys
from orchestrator.core import AgentOrchestrator

# Configure logging to see the distribution of tasks
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

async def test_load_balancing():
    print("\n--- Testing Load Balancing (Burst of 10 tasks) ---")
    orchestrator = AgentOrchestrator()
    await orchestrator.connect()
    
    # We send a burst of 10 tasks to 'tasks.lighting'.
    # Since we have 3 agent replicas in a Queue Group, 
    # NATS should distribute these tasks among them.
    tasks = []
    for i in range(10):
        payload = {
            "device_id": f"light_{i:02d}",
            "state": "on",
            "brightness": 70,
            "ambient_light": 300
        }
        # We create the task but don't await it immediately to send them as a burst
        tasks.append(orchestrator.send_task(
            subject="tasks.lighting", 
            payload=payload
        ))
    
    print(f"Sent {len(tasks)} tasks. Awaiting results...")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
    print(f"Completed: {success_count}/10 tasks successful.")
    
    await orchestrator.close()

async def main():
    await test_load_balancing()

if __name__ == "__main__":
    asyncio.run(main())
