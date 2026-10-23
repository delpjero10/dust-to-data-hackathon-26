# Convenience targets for controlling the Bosch Spotless BCRD2W from the terminal
# (no opencode needed). Run from the repo root, or use
#   make -C ~/Code/dust-to-data-hackathon-26 start
#
# Examples (full reference: docs/home-connect-control.md):
#   make start                              # start cleaning (CleanAll)
#   make stop                               # stop cleaning
#   make status                             # live status
#   make chat MESSAGE="start cleaning"      # AI layer (natural language)
#   make watch ARGS="--interval 2"          # pass extra CLI args via ARGS
#   make coverage-live COLLECT_SECONDS=60   # collect the path 60 s, then analyze
#   make obstacles AUTO=1 YES=1             # detect + auto-recover (real device)

PYTHON ?= python3
CLI := $(PYTHON) -m src.cli
# Extra CLI arguments, e.g.  make coverage ARGS="--map-id 123 --collect 30"
ARGS :=

.DEFAULT_GOAL := help

.PHONY: help login appliances status programs start stop dock chat settings maps robot summaries smart-empty watch coverage coverage-live obstacles test

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F'[:#]' '{printf "  %-14s %s\n", $$1, $$3}'

login: ## One-time OAuth login (stores token in .token.json)
	$(CLI) login

appliances: ## List paired appliances
	$(CLI) appliances

status: ## Live device status
	$(CLI) status

programs: ## List available programs
	$(CLI) programs

start: ## Start cleaning (CleanAll)
	$(CLI) start

stop: ## Stop the active program
	$(CLI) stop

dock: ## Send the robot back to base (GoHome program)
	$(CLI) dock

chat: ## AI layer, natural language: make chat MESSAGE="start cleaning"
	$(CLI) chat "$(MESSAGE)"

settings: ## List device settings
	$(CLI) settings

maps: ## List robot maps
	$(CLI) maps

robot: ## Show robot position
	$(CLI) robot

summaries: ## Show cleaning summaries
	$(CLI) summaries

smart-empty: ## Smart Emptying verdict for the current session
	$(CLI) smart-empty

watch: ## Smart Emptying (live): flag a false empty when the robot docks
	$(CLI) watch $(ARGS)

coverage: ## Coverage analysis + fake-cleaning detection from the map
	$(CLI) coverage $(ARGS)

COLLECT_SECONDS ?= 45
coverage-live: ## Coverage: collect the cleaning path live, then analyze (COLLECT_SECONDS=45)
	$(CLI) coverage --collect $(COLLECT_SECONDS) $(ARGS)

obstacles: ## Obstacle-loop detection (AI layer); add AUTO=1 to also recover the robot
	$(CLI) obstacles $(ARGS) $(if $(AUTO),--auto $(if $(YES),--yes,),)

test: ## Run unit tests (stdlib unittest)
	$(PYTHON) -m unittest discover -s tests -v
