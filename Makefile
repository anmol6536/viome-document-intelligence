ifneq (,$(wildcard .env))
include .env
export
endif

AIDBOX_HOST ?= localhost
AIDBOX_PORT ?= 8080

# Reserved host port block for this project (see docker-compose.yml):
#   8020 - app (FastAPI)
#   8021 - validator (HL7 FHIR validator sidecar)
# This machine runs several 8xxx "health data" services - if these
# collide with something else, pick a free slot and update both here
# and in docker-compose.yml / .env's FHIR_VALIDATOR_URL.
APP_PORT ?= 8020
VALIDATOR_PORT ?= 8021

STRUCTURE_DEFINITION := fhir-ig/fsh-generated/resources/StructureDefinition-viome-lab-observation.json

.PHONY: init sushi-build aidbox-register up down logs

## init: build the FHIR profile with SUSHI and register it with Aidbox
init: sushi-build aidbox-register

## up: build and start the app + validator via docker compose
up:
	docker compose up --build -d
	@echo "app:       http://localhost:$(APP_PORT)"
	@echo "validator: http://localhost:$(VALIDATOR_PORT)"

## down: stop the docker compose stack
down:
	docker compose down

## logs: tail docker compose logs for both services
logs:
	docker compose logs -f

## sushi-build: compile fhir-ig/input/fsh into StructureDefinition JSON
sushi-build:
	cd fhir-ig && sushi build .

## aidbox-register: PUT the compiled viome-lab-observation profile into Aidbox
aidbox-register:
	@test -n "$(AIDBOX_SECRET)" || (echo "AIDBOX_SECRET is not set (check .env)" >&2 && exit 1)
	@test -f "$(STRUCTURE_DEFINITION)" || (echo "$(STRUCTURE_DEFINITION) not found - run 'make sushi-build' first" >&2 && exit 1)
	curl -sf -X PUT "http://$(AIDBOX_HOST):$(AIDBOX_PORT)/fhir/StructureDefinition/viome-lab-observation" \
		-H "Content-Type: application/json" \
		-u "root:$(AIDBOX_SECRET)" \
		-d @$(STRUCTURE_DEFINITION) \
		&& echo "\nRegistered viome-lab-observation profile with Aidbox at $(AIDBOX_HOST):$(AIDBOX_PORT)"
