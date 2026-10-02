.DEFAULT_GOAL := help

ifeq ($(OS),Windows_NT)
PYTHON ?= python
else
PYTHON ?= python3
endif

# Defaults are resolved by Python, including PI_CODING_AGENT_DIR.
AGENT_DIR ?=
ARCHIVE ?=
OUTPUT ?=
FLAGS ?=
AGENT_ARG = $(if $(AGENT_DIR),--agent-dir "$(AGENT_DIR)",)

.PHONY: help backup restore restore-preview test
help:
	@echo "make backup [OUTPUT=backups/my-config.zip]"
	@echo "make restore-preview ARCHIVE=backups/my-config.zip"
	@echo "make restore ARCHIVE=backups/my-config.zip [FLAGS=--yes]"
	@echo "Options: AGENT_DIR=path PYTHON=python3"
	@echo "make test"

backup:
	$(PYTHON) scripts/pi_config.py $(AGENT_ARG) backup $(if $(OUTPUT),--output "$(OUTPUT)",) $(FLAGS)

restore-preview:
	$(PYTHON) scripts/pi_config.py $(AGENT_ARG) restore --archive "$(ARCHIVE)" --dry-run

restore:
	$(PYTHON) scripts/pi_config.py $(AGENT_ARG) restore --archive "$(ARCHIVE)" $(FLAGS)

test:
	$(PYTHON) -m unittest discover -s tests -v
