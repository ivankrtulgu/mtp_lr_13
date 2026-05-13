// Package models defines the data structures used by the Lighting Agent
// to communicate with the Smart Home Multi-Agent System orchestrator.
package models

import (
	"encoding/json"
	"time"
)

// Task represents a unit of work sent by the orchestrator on the
// "tasks.lighting" NATS subject.
type Task struct {
	// ID is a unique identifier for the task.
	ID string `json:"id"`

	// Type indicates the kind of operation to perform (e.g. "set_state").
	Type string `json:"type"`

	// Payload holds the type-specific parameters as raw JSON.
	Payload json.RawMessage `json:"payload"`

	// Timestamp is the time at which the task was created.
	Timestamp time.Time `json:"timestamp"`
}

// LightingParams contains the parameters for a "set_state" operation.
type LightingParams struct {
	// DeviceID identifies the lighting device (e.g. "light-living-room").
	DeviceID string `json:"device_id"`

	// State is the desired state: "on" or "off".
	State string `json:"state"`

	// Brightness is the desired brightness level (0–100).
	Brightness int `json:"brightness"`

	// AmbientLight is the current ambient light reading in lux.
	AmbientLight int `json:"ambient_light"`
}

// Result is the outcome of a task, published to the "tasks.completed"
// NATS subject by the agent.
type Result struct {
	// TaskID links the result back to the originating task.
	TaskID string `json:"task_id"`

	// Success indicates whether the task completed without error.
	Success bool `json:"success"`

	// Data holds the operation-specific result payload.
	Data interface{} `json:"data,omitempty"`

	// Error contains a human-readable error message when Success is false.
	Error string `json:"error,omitempty"`

	// Timestamp is the time at which the result was generated.
	Timestamp time.Time `json:"timestamp"`
}

// LightingResultData holds the enriched result of a lighting operation,
// including any automatic adjustments made by the agent.
type LightingResultData struct {
	// DeviceID identifies the lighting device that was operated on.
	DeviceID string `json:"device_id"`

	// State is the final (possibly overridden) state of the device.
	State string `json:"state"`

	// Brightness is the final brightness level applied.
	Brightness int `json:"brightness"`

	// AmbientLight is the ambient light reading that was used in decision
	// making.
	AmbientLight int `json:"ambient_light"`

	// AutoTriggered is true when the agent automatically turned the light
	// on because ambient light fell below the threshold.
	AutoTriggered bool `json:"auto_triggered"`
}
