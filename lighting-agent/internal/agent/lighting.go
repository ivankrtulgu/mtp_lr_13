// Package agent implements the Lighting Agent that processes lighting
// tasks from the Smart Home orchestrator via NATS messaging.
package agent

import (
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/nats-io/nats.go"

	"github.com/smarthome/lighting-agent/internal/models"
)

// AmbientThreshold is the ambient light level (in lux) below which the agent
// automatically forces the light to turn on, regardless of the requested
// state.
const AmbientThreshold = 200

// Agent represents the Lighting Agent. It holds a NATS connection, a
// subscription handle, and a logger. Use [New] to create instances; do not
// zero-initialise.
type Agent struct {
	conn   *nats.Conn
	logger *log.Logger
	sub    *nats.Subscription
}

// New creates a new Agent bound to the given NATS connection. If logger is
// nil, [log.Default] is used.
func New(conn *nats.Conn, logger *log.Logger) *Agent {
	if logger == nil {
		logger = log.Default()
	}
	return &Agent{
		conn:   conn,
		logger: logger,
	}
}

// Start subscribes to the "tasks.lighting" NATS subject and begins
// processing incoming tasks synchronously. It returns an error if the
// subscription fails.
func (a *Agent) Start() error {
	var err error
	a.sub, err = a.conn.Subscribe("tasks.lighting", a.handleMessage)
	if err != nil {
		return fmt.Errorf("subscribe to tasks.lighting: %w", err)
	}

	// Flush to ensure the subscription is registered with the server.
	if err := a.conn.Flush(); err != nil {
		return fmt.Errorf("flush subscription: %w", err)
	}

	a.logger.Println("Agent started — subscribed to 'tasks.lighting'")
	return nil
}

// Stop unsubscribes from "tasks.lighting". It is safe to call multiple
// times.
func (a *Agent) Stop() {
	if a.sub == nil {
		return
	}
	if err := a.sub.Unsubscribe(); err != nil {
		a.logger.Printf("Error unsubscribing: %v", err)
		return
	}
	a.sub = nil
	a.logger.Println("Unsubscribed from 'tasks.lighting'")
}

// handleMessage is the NATS message handler. It unmarshals the incoming
// JSON as a [models.Task] and dispatches to the appropriate business-logic
// method.
func (a *Agent) handleMessage(m *nats.Msg) {
	var task models.Task
	if err := json.Unmarshal(m.Data, &task); err != nil {
		a.logger.Printf("Failed to parse task JSON: %v", err)
		a.publishResult(models.Result{
			TaskID:    "unknown",
			Success:   false,
			Error:     fmt.Sprintf("invalid task JSON: %v", err),
			Timestamp: time.Now().UTC(),
		})
		return
	}

	a.logger.Printf("Received task: id=%q type=%q", task.ID, task.Type)

	var result models.Result
	switch task.Type {
	case "set_state":
		result = a.handleSetState(task)
	default:
		result = models.Result{
			TaskID:    task.ID,
			Success:   false,
			Error:     fmt.Sprintf("unknown task type: %q", task.Type),
			Timestamp: time.Now().UTC(),
		}
	}

	a.publishResult(result)
}

// handleSetState processes a "set_state" task. It unmarshals the payload as
// [models.LightingParams] and applies the auto-trigger rule:
//
//   - If ambient_light < AmbientThreshold (200) the light state is forced to
//     "on" and the brightness is set to at least 100.
//
// The result contains the final (possibly overridden) state and an
// auto_triggered flag.
func (a *Agent) handleSetState(task models.Task) models.Result {
	var params models.LightingParams
	if err := json.Unmarshal(task.Payload, &params); err != nil {
		return models.Result{
			TaskID:    task.ID,
			Success:   false,
			Error:     fmt.Sprintf("invalid lighting params: %v", err),
			Timestamp: time.Now().UTC(),
		}
	}

	a.logger.Printf("set_state: device=%q state=%q brightness=%d ambient=%d",
		params.DeviceID, params.State, params.Brightness, params.AmbientLight)

	// Default values.
	effectiveState := params.State
	effectiveBrightness := params.Brightness
	autoTriggered := false

	// Auto-trigger rule: when ambient light is too low, force the light ON.
	if params.AmbientLight < AmbientThreshold {
		a.logger.Printf("Ambient light %d < %d: auto-triggering light ON",
			params.AmbientLight, AmbientThreshold)

		effectiveState = "on"
		autoTriggered = true

		// Ensure minimum brightness when auto-triggering.
		if effectiveBrightness <= 0 {
			effectiveBrightness = 100
		}
	}

	data := models.LightingResultData{
		DeviceID:      params.DeviceID,
		State:         effectiveState,
		Brightness:    effectiveBrightness,
		AmbientLight:  params.AmbientLight,
		AutoTriggered: autoTriggered,
	}

	return models.Result{
		TaskID:    task.ID,
		Success:   true,
		Data:      data,
		Timestamp: time.Now().UTC(),
	}
}

// publishResult serialises a [models.Result] and publishes it to the
// "tasks.completed" NATS subject. Errors are logged; they are not returned
// because this runs inside the message handler goroutine.
func (a *Agent) publishResult(result models.Result) {
	data, err := json.Marshal(result)
	if err != nil {
		a.logger.Printf("Failed to marshal result: %v", err)
		return
	}

	if err := a.conn.Publish("tasks.completed", data); err != nil {
		a.logger.Printf("Failed to publish result to 'tasks.completed': %v", err)
		return
	}

	a.logger.Printf("Published result: task_id=%q success=%v", result.TaskID, result.Success)
}
