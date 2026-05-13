// Command lighting-agent is a NATS-based microservice for the Smart Home
// Multi-Agent System. It subscribes to "tasks.lighting", processes
// "set_state" commands (with automatic light activation when ambient light
// is low), and publishes results to "tasks.completed".
package main

import (
	"io"
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
	// Open agent.log in append mode — create if it doesn't exist.
	logFile, err := os.OpenFile("agent.log", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		log.Fatalf("[FATAL] Failed to open agent.log: %v", err)
	}
	defer logFile.Close()

	// Dual logging: write to both stdout and agent.log.
	multiWriter := io.MultiWriter(os.Stdout, logFile)
	logger := log.New(multiWriter, "", log.LstdFlags|log.Lmicroseconds)

	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = defaultNATSURL
	}

	logger.Printf("[INFO] Connecting to NATS at %s", natsURL)

	nc, err := nats.Connect(natsURL,
		nats.Name("lighting-agent"),
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(10),
		nats.ReconnectWait(2*time.Second),
	)
	if err != nil {
		logger.Printf("[FATAL] Failed to connect to NATS: %v", err)
		os.Exit(1)
	}
	defer nc.Close()

	logger.Printf("[INFO] Connected to NATS")

	// Create and start the agent.
	ag := agent.New(nc, logger)
	if err := ag.Start(); err != nil {
		logger.Printf("[FATAL] Failed to start agent: %v", err)
		os.Exit(1)
	}

	// Wait for OS interrupt / terminate signal.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	sig := <-sigCh

	logger.Printf("[INFO] Received signal %v — shutting down gracefully...", sig)

	// Stop the agent (unsubscribe).
	ag.Stop()

	// Drain the NATS connection so pending published messages are flushed.
	_ = nc.Drain() // Drain logs internally; ignore error on shutdown.

	logger.Printf("[INFO] Shutdown complete.")
}
