import asyncio
import logging
import sys
from orchestrator.core import AgentOrchestrator

# Configure logging to see the retries in console
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

async def test_timeout_retries():
    print("\n--- Testing Timeout Retries (Expecting 3 attempts) ---")
    orchestrator = AgentOrchestrator()
    await orchestrator.connect()
    
    try:
        # Send to a subject that NO agent is listening to
        # Timeout is set very short for the test (1s)
        await orchestrator.send_task(
            subject="tasks.void", 
            payload={"test": "data"}, 
            timeout=1.0
        )
    except TimeoutError:
        print("[SUCCESS] Received expected TimeoutError after retries.")
    except Exception as e:
        print(f"[FAILURE] Received unexpected exception: {type(e).__name__}: {e}")
    finally:
        await orchestrator.close()

async def test_connection_retries():
    print("\n--- Testing Connection Retries (Expecting 3 attempts) ---")
    orchestrator = AgentOrchestrator()
    # We intentionally DO NOT call orchestrator.connect()
    
    try:
        await orchestrator.send_task(
            subject="tasks.lighting", 
            payload={"test": "data"}, 
            timeout=1.0
        )
    except ConnectionError:
        print("[SUCCESS] Received expected ConnectionError after retries.")
    except Exception as e:
        print(f"[FAILURE] Received unexpected exception: {type(e).__name__}: {e}")
    finally:
        await orchestrator.close()

async def main():
    await test_timeout_retries()
    await test_connection_retries()

if __name__ == "__main__":
    asyncio.run(main())
