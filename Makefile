SHELL := /bin/bash

.PHONY: auto inspect monitor summarize

TIMESTAMP := $(shell date -u +%Y-%m-%dT%H%M%SZ)
DATE := $(shell date -u +%F)

auto:
	@if [ -z "$(CLAIM)" ]; then echo "Usage: make auto CLAIM=\"your claim\""; exit 1; fi
	@mkdir -p runs/auto
	@echo "Running Auto-RPL for: $(CLAIM)"
	@uv run heretix-rpl auto --claim "$(CLAIM)" --out runs/auto/$(TIMESTAMP).json
	@uv run heretix-rpl inspect --run runs/auto/$(TIMESTAMP).json

inspect:
	@if [ -z "$(FILE)" ]; then echo "Usage: make inspect FILE=path/to/run.json"; exit 1; fi
	@uv run heretix-rpl inspect --run "$(FILE)"

monitor:
	@mkdir -p runs/monitor
	@echo "Running sentinel monitor to runs/monitor/$(DATE).jsonl"
	@uv run heretix-rpl monitor --bench bench/sentinels.json --out runs/monitor/$(DATE).jsonl $(EXTRA)

summarize:
	@if [ -z "$(FILE)" ]; then echo "Usage: make summarize FILE=runs/monitor/<date>.jsonl"; exit 1; fi
	@uv run heretix-rpl summarize --file "$(FILE)"

