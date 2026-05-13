package agent

import (
	"encoding/json"
	"log"
	"os"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/smarthome/lighting-agent/internal/models"
)

func TestHandleSetState(t *testing.T) {
	// Setup agent with a dummy logger to avoid polluting test output
	logger := log.New(os.Stdout, "TEST: ", log.LstdFlags)
	agent := New(nil, logger)

	tests := []struct {
		name           string
		task           models.Task
		wantSuccess    bool
		wantState      string
		wantBrightness int
		wantAuto       bool
		wantErr        bool
	}{
		{
			name: "Normal operation - state obeyed",
			task: models.Task{
				ID: "t1",
				Payload: json.RawMessage(`{
					"device_id": "light-1",
					"state": "off",
					"brightness": 50,
					"ambient_light": 300
				}`),
			},
			wantSuccess:    true,
			wantState:      "off",
			wantBrightness: 50,
			wantAuto:       false,
			wantErr:        false,
		},
		{
			name: "Auto-trigger - force ON",
			task: models.Task{
				ID: "t2",
				Payload: json.RawMessage(`{
					"device_id": "light-1",
					"state": "off",
					"brightness": 50,
					"ambient_light": 100
				}`),
			},
			wantSuccess:    true,
			wantState:      "on",
			wantBrightness: 50,
			wantAuto:       true,
			wantErr:        false,
		},
		{
			name: "Auto-trigger - force ON and min brightness",
			task: models.Task{
				ID: "t3",
				Payload: json.RawMessage(`{
					"device_id": "light-1",
					"state": "off",
					"brightness": 0,
					"ambient_light": 100
				}`),
			},
			wantSuccess:    true,
			wantState:      "on",
			wantBrightness: 100,
			wantAuto:       true,
			wantErr:        false,
		},
		{
			name: "Auto-trigger - already ON",
			task: models.Task{
				ID: "t4",
				Payload: json.RawMessage(`{
					"device_id": "light-1",
					"state": "on",
					"brightness": 50,
					"ambient_light": 100
				}`),
			},
			wantSuccess:    true,
			wantState:      "on",
			wantBrightness: 50,
			wantAuto:       true,
			wantErr:        false,
		},
		{
			name: "Invalid JSON payload",
			task: models.Task{
				ID:      "t5",
				Payload: json.RawMessage(`{ "invalid": "json" `), // Missing closing brace
			},
			wantSuccess: false,
			wantErr:     true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := agent.handleSetState(tt.task)

			if result.Success != tt.wantSuccess {
				t.Errorf("Success = %v, want %v", result.Success, tt.wantSuccess)
			}

			if tt.wantErr && result.Error == "" {
				t.Error("Expected error but got none")
			}

			if tt.wantSuccess {
				data, ok := result.Data.(models.LightingResultData)
				if !ok {
					t.Fatalf("Result data is not of type models.LightingResultData")
				}
				if data.State != tt.wantState {
					t.Errorf("State = %q, want %q", data.State, tt.wantState)
				}
				if data.Brightness != tt.wantBrightness {
					t.Errorf("Brightness = %d, want %d", data.Brightness, tt.wantBrightness)
				}
				if data.AutoTriggered != tt.wantAuto {
					t.Errorf("AutoTriggered = %v, want %v", data.AutoTriggered, tt.wantAuto)
				}
			}
		})
	}
}

func TestHandleMessage(t *testing.T) {
	// Use a dummy NATS connection to avoid panics in publishResult
	dummyConn := &nats.Conn{}
	logger := log.New(os.Stdout, "TEST: ", log.LstdFlags)
	agent := New(dummyConn, logger)

	tests := []struct {
		name    string
		message *nats.Msg
	}{
		{
			name: "Valid set_state task",
			message: &nats.Msg{
				Data: []byte(`{
					"id": "m1",
					"type": "set_state",
					"payload": {
						"device_id": "light-1",
						"state": "on",
						"brightness": 80,
						"ambient_light": 300
					}
				}`),
			},
		},
		{
			name: "Unknown task type",
			message: &nats.Msg{
				Data: []byte(`{
					"id": "m2",
					"type": "unknown_type",
					"payload": {}
				}`),
			},
		},
		{
			name: "Malformed JSON",
			message: &nats.Msg{
				Data: []byte(`{ "bad": "json" `),
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// We are primarily testing that handleMessage does not panic
			// and processes the input. Since we can't easily verify the
			// published result without a real NATS server, we check for panics.
			defer func() {
				if r := recover(); r != nil {
					t.Errorf("handleMessage panicked: %v", r)
				}
			}()
			agent.handleMessage(tt.message)
		})
	}
}
