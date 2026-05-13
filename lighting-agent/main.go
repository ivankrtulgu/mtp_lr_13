// Command lighting-agent is a NATS-based microservice for the Smart Home
// Multi-Agent System. It subscribes to "tasks.lighting", processes
// "set_state" commands (with automatic light activation when ambient light
// is low), and publishes results to "tasks.completed".
package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/nats-io/nats.go"

	"github.com/smarthome/lighting-agent/internal/agent"
)

const defaultNATSURL = "nats://localhost:4222"

func main() {
	logger := log.New(os.Stdout, "[lighting-agent] ", log.LstdFlags|log.Lmicroseconds)

	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = defaultNATSURL
	}

	logger.Printf("Connecting to NATS at %s", natsURL)

	nc, err := nats.Connect(natsURL,
		nats.Name("lighting-agent"),
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(10),
		nats.ReconnectWait(2*time.Second),
	)
	if err != nil {
		logger.Fatalf("Failed to connect to NATS: %v", err)
	}
	defer nc.Close()

	logger.Println("Connected to NATS")

	// Create and start the agent.
	ag := agent.New(nc, logger)
	if err := ag.Start(); err != nil {
		logger.Fatalf("Failed to start agent: %v", err)
	}

	// Wait for OS interrupt / terminate signal.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	sig := <-sigCh

	logger.Printf("Received signal %v — shutting down gracefully...", sig)

	// Stop the agent (unsubscribe).
	ag.Stop()

	// Drain the NATS connection so pending published messages are flushed.
	_ = nc.Drain() // Drain logs internally; ignore error on shutdown.

	logger.Println("Shutdown complete.")
}
