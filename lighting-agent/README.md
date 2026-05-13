# Lighting Agent

A **Go-based Lighting Agent** for the Smart Home Multi-Agent System (MAS).
This agent listens for lighting tasks over NATS and publishes results back to
the orchestrator.

## Architecture

```
┌──────────────┐   tasks.lighting   ┌─────────────────┐   tasks.completed   ┌──────────────┐
│ Orchestrator │ ──────────────────▶│  Lighting Agent  │ ──────────────────▶│  Orchestrator │
│   (NATS Pub) │                    │  (NATS Sub)      │                    │   (NATS Sub)  │
└──────────────┘                    └─────────────────┘                    └──────────────┘
```

The agent subscribes to the **`tasks.lighting`** subject, processes the
incoming task, and publishes the result to **`tasks.completed`**.

## Features

- **`set_state`** command — change a light's state (`on`/`off`) and
  brightness.
- **Auto-trigger** — When the reported ambient light is below 200 lux, the
  agent automatically forces the light **on** regardless of the requested
  state.
- Graceful shutdown on `SIGINT` / `SIGTERM`.
- Robust JSON parsing — malformed messages are reported as errors, never
  cause panics.
- Structured logging via the standard `log` package.

## Prerequisites

- [Go](https://go.dev/dl/) 1.21 or later
- A running [NATS Server](https://nats.io/download/) (default:
  `nats://localhost:4222`)

## Building

```bash
cd lighting-agent
go build -o lighting-agent.exe .
```

## Running

### 1. Start NATS

```bash
nats-server
```

### 2. Start the Lighting Agent

```bash
# Default NATS URL (localhost:4222)
go run .

# Or specify a custom NATS URL
set NATS_URL=nats://nats.example.com:4222
go run .
```

The agent logs its activity to stdout:

```
[lighting-agent] 2026/05/13 12:00:00.123456 Connecting to NATS at nats://localhost:4222
[lighting-agent] 2026/05/13 12:00:00.234567 Connected to NATS
[lighting-agent] 2026/05/13 12:00:00.234567 Agent started — subscribed to 'tasks.lighting'
```

## Usage

### Send a task with `nats pub`

**Set a light on (ambient light is adequate — no auto-trigger):**

```bash
nats pub tasks.lighting '{
  "id": "task-001",
  "type": "set_state",
  "payload": {
    "device_id": "light-living-room",
    "state": "on",
    "brightness": 80,
    "ambient_light": 400
  },
  "timestamp": "2026-05-13T12:00:00Z"
}'
```

Expected result on `tasks.completed`:

```json
{
  "task_id": "task-001",
  "success": true,
  "data": {
    "device_id": "light-living-room",
    "state": "on",
    "brightness": 80,
    "ambient_light": 400,
    "auto_triggered": false
  },
  "timestamp": "2026-05-13T12:00:01Z"
}
```

### Auto-trigger example

**Ambient light is below 200 lux — agent forces light on:**

```bash
nats pub tasks.lighting '{
  "id": "task-002",
  "type": "set_state",
  "payload": {
    "device_id": "light-bedroom",
    "state": "off",
    "brightness": 0,
    "ambient_light": 50
  },
  "timestamp": "2026-05-13T12:05:00Z"
}'
```

Expected result:

```json
{
  "task_id": "task-002",
  "success": true,
  "data": {
    "device_id": "light-bedroom",
    "state": "on",
    "brightness": 100,
    "ambient_light": 50,
    "auto_triggered": true
  },
  "timestamp": "2026-05-13T12:05:01Z"
}
```

Notice:
- `state` was overridden from `"off"` to `"on"`.
- `brightness` was bumped from `0` to `100`.
- `auto_triggered` is `true`.

### Invalid task example

```bash
nats pub tasks.lighting '{"bad": "json"}'
```

The agent logs the error and publishes a failure result:

```json
{
  "task_id": "unknown",
  "success": false,
  "error": "invalid task JSON: json: unknown field \"bad\"",
  "timestamp": "2026-05-13T12:10:01Z"
}
```

**No panics — only graceful error reporting.**

## Data Models

### Task (received on `tasks.lighting`)

| Field       | Type            | Description                              |
|-------------|-----------------|------------------------------------------|
| `id`        | `string`        | Unique task identifier                   |
| `type`      | `string`        | Operation type (e.g. `"set_state"`)      |
| `payload`   | `JSON object`   | Type-specific parameters (see below)     |
| `timestamp` | `ISO‑8601`      | Task creation time                       |

### LightingParams (inside `payload`)

| Field           | Type     | Description                          |
|-----------------|----------|--------------------------------------|
| `device_id`     | `string` | Device identifier                    |
| `state`         | `string` | Desired state: `"on"` or `"off"`     |
| `brightness`    | `int`    | Brightness 0–100                     |
| `ambient_light` | `int`    | Current ambient light in lux         |

### Result (published to `tasks.completed`)

| Field       | Type            | Description                              |
|-------------|-----------------|------------------------------------------|
| `task_id`   | `string`        | Origin task ID                           |
| `success`   | `bool`          | Whether the task succeeded                |
| `data`      | `JSON object`   | Operation result (on success)            |
| `error`     | `string`        | Error message (on failure)               |
| `timestamp` | `ISO‑8601`      | Result generation time                   |

### LightingResultData (inside `data`)

| Field           | Type     | Description                               |
|-----------------|----------|-------------------------------------------|
| `device_id`     | `string` | Device identifier                         |
| `state`         | `string` | Final state (possibly overridden)         |
| `brightness`    | `int`    | Final brightness                          |
| `ambient_light` | `int`    | Ambient light reading used in decision    |
| `auto_triggered`| `bool`   | Whether auto-trigger rule was applied     |

## Project Structure

```
lighting-agent/
├── go.mod                  # Module definition (github.com/smarthome/lighting-agent)
├── go.sum                  # Dependency checksums
├── main.go                 # Entry point — NATS connection, signal handling
├── README.md               # This file
└── internal/
    ├── agent/
    │   └── lighting.go     # Agent struct, task dispatch, set_state handler
    └── models/
        └── models.go       # Task, Result, LightingParams, LightingResultData
```

## Testing (manual)

1. Start a NATS server.
2. Subscribe to `tasks.completed` to observe results:
   ```bash
   nats sub tasks.completed
   ```
3. In another terminal, start the agent:
   ```bash
   go run .
   ```
4. Publish tasks as shown in the examples above.
