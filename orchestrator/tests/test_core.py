import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from orchestrator.core import AgentOrchestrator
from orchestrator.models import ResultModel
from nats.aio.msg import Msg as NatsMsg

@pytest.fixture
def orchestrator():
    return AgentOrchestrator(nats_url="nats://localhost:4222")

@pytest.fixture
def mock_nats_conn():
    conn = AsyncMock()
    # Mock subscribe to return a mock subscription
    sub = AsyncMock()
    conn.subscribe.return_value = sub
    return conn

@pytest.mark.asyncio
async def test_connect(orchestrator, mock_nats_conn):
    with patch("nats.connect", return_value=mock_nats_conn) as mock_connect:
        await orchestrator.connect()
        
        mock_connect.assert_called_once_with(
            "nats://localhost:4222",
            name="agent-orchestrator",
            reconnect_time_wait=2,
            max_reconnect_attempts=10,
        )
        mock_nats_conn.subscribe.assert_called_once_with(
            orchestrator.DEFAULT_RESULT_SUBJECT,
            cb=orchestrator._on_result,
        )
        assert orchestrator.nc == mock_nats_conn

@pytest.mark.asyncio
async def test_close(orchestrator, mock_nats_conn):
    with patch("nats.connect", return_value=mock_nats_conn):
        await orchestrator.connect()
        
        # Create a pending future to test cancellation
        fut = asyncio.get_event_loop().create_future()
        orchestrator._pending["test_task"] = fut
        
        await orchestrator.close()
        
        assert fut.cancelled()
        assert len(orchestrator._pending) == 0
        mock_nats_conn.drain.assert_called_once()
        assert orchestrator.nc is None

@pytest.mark.asyncio
async def test_send_task_success(orchestrator, mock_nats_conn):
    with patch("nats.connect", return_value=mock_nats_conn):
        await orchestrator.connect()
        
        subject = "tasks.lighting"
        payload = {"device_id": "light_1", "state": "on"}
        
        # We need to simulate the asynchronous response.
        # Since send_task awaits a future, we'll run it in a task and then trigger _on_result.
        task = asyncio.create_task(orchestrator.send_task(subject, payload))
        
        # Give the event loop a chance to run send_task up to the await point
        await asyncio.sleep(0)
        
        # Find the task_id that was generated
        task_id = list(orchestrator._pending.keys())[0]
        
        # Create a mock NATS message with a ResultModel
        result_data = ResultModel(
            task_id=task_id,
            success=True,
            data={"status": "ok"},
            timestamp="2026-05-13T10:00:00Z"
        )
        
        mock_msg = MagicMock(spec=NatsMsg)
        mock_msg.data = result_data.model_dump_json().encode("utf-8")
        
        # Trigger the callback
        await orchestrator._on_result(mock_msg)
        
        result = await task
        assert result["success"] is True
        assert result["data"] == {"status": "ok"}
        mock_nats_conn.publish.assert_called_once()

@pytest.mark.asyncio
async def test_send_task_timeout(orchestrator, mock_nats_conn):
    with patch("nats.connect", return_value=mock_nats_conn):
        await orchestrator.connect()
        
        # Use a very short timeout to trigger TimeoutError quickly
        with pytest.raises(TimeoutError):
            await orchestrator.send_task("tasks.test", {"foo": "bar"}, timeout=0.1)
        
        # It should have tried 3 times (initial + 2 retries)
        assert mock_nats_conn.publish.call_count == 3

@pytest.mark.asyncio
async def test_send_task_retry_success(orchestrator, mock_nats_conn):
    with patch("nats.connect", return_value=mock_nats_conn):
        await orchestrator.connect()
        
        # Mock publish to fail twice then succeed
        # Note: send_task catches (TimeoutError, ConnectionError)
        mock_nats_conn.publish.side_effect = [
            TimeoutError("First fail"),
            ConnectionError("Second fail"),
            None # Third success
        ]
        
        # To make this test fast, we need to mock asyncio.sleep
        with patch("asyncio.sleep", return_value=None):
            # We need to simulate a result arriving for the 3rd attempt
            # because send_task will await the future after the 3rd publish.
            
            async def simulate_result():
                # Wait until the 3rd publish happens
                while mock_nats_conn.publish.call_count < 3:
                    await asyncio.sleep(0)
                
                task_id = list(orchestrator._pending.keys())[0]
                result_data = ResultModel(
                    task_id=task_id,
                    success=True,
                    data={"status": "recovered"},
                    timestamp="2026-05-13T10:00:00Z"
                )
                mock_msg = MagicMock(spec=NatsMsg)
                mock_msg.data = result_data.model_dump_json().encode("utf-8")
                await orchestrator._on_result(mock_msg)

            # Run simulation in background
            sim_task = asyncio.create_task(simulate_result())
            
            result = await orchestrator.send_task("tasks.test", {"foo": "bar"}, timeout=1.0)
            
            assert result["data"] == {"status": "recovered"}
            assert mock_nats_conn.publish.call_count == 3
            sim_task.cancel()

@pytest.mark.asyncio
async def test_on_result_correlation(orchestrator):
    # Setup two pending futures
    fut1 = asyncio.get_event_loop().create_future()
    fut2 = asyncio.get_event_loop().create_future()
    orchestrator._pending["task_1"] = fut1
    orchestrator._pending["task_2"] = fut2
    
    # 1. Result for task_1
    res1 = ResultModel(task_id="task_1", success=True, data="res1", timestamp="...")
    msg1 = MagicMock(spec=NatsMsg)
    msg1.data = res1.model_dump_json().encode("utf-8")
    await orchestrator._on_result(msg1)
    
    assert fut1.done()
    assert fut1.result()["data"] == "res1"
    assert not fut2.done()
    
    # 2. Result for unknown task
    res_unknown = ResultModel(task_id="unknown", success=True, data="res_u", timestamp="...")
    msg_u = MagicMock(spec=NatsMsg)
    msg_u.data = res_unknown.model_dump_json().encode("utf-8")
    await orchestrator._on_result(msg_u)
    
    assert not fut2.done() # task_2 should still be pending
