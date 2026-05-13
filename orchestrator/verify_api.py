import asyncio
import httpx
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

async def test_api_endpoint():
    print("\n--- Testing FastAPI Endpoint /tasks ---")
    
    # The API is expected to run at http://127.0.0.1:8000
    url = "http://127.0.0.1:8000/tasks"
    
    # Payload for the lighting agent
    payload = {
        "subject": "tasks.lighting",
        "payload": {
            "device_id": "light_api_01",
            "state": "on",
            "brightness": 80,
            "ambient_light": 300
        },
        "task_type": "set_state",
        "timeout": 5.0
    }
    
    async with httpx.AsyncClient() as client:
        try:
            logger.info("Sending POST request to %s", url)
            response = await client.post(url, json=payload)
            
            print(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                print("Response JSON:")
                print(response.json())
                print("\n[SUCCESS] API correctly triggered the task and returned a result.")
            else:
                print(f"Unexpected status code: {response.status_code}")
                print(f"Response body: {response.text}")
                print("\n[FAILURE] API returned an error.")
                
        except httpx.ConnectError:
            print("\n[FAILURE] Could not connect to FastAPI server. Is it running?")
            print("Run: uvicorn orchestrator.api:app --reload")
        except Exception as e:
            print(f"\n[FAILURE] An unexpected error occurred: {e}")

async def main():
    await test_api_endpoint()

if __name__ == "__main__":
    asyncio.run(main())
