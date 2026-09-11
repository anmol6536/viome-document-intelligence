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
ORGANIZATION := fhir-ig/fsh-generated/resources/Organization-viome-document-intelligence-organization.json

.PHONY: init sushi-build aidbox-register aidbox-register-org up down logs

## init: build the FHIR profile with SUSHI and register it (+ our Organization) with Aidbox
init: sushi-build aidbox-register aidbox-register-org

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

## aidbox-register-org: PUT the viome-document-intelligence source Organization into Aidbox
## NOTE: best-guess shape (identifier system/value) for the gateway's
## provider->Organization lookup - not yet confirmed against its actual
## query. If the gateway still can't resolve this provider afterward,
## check what it really searches on and update fhir-ig/input/fsh/organization.fsh.
aidbox-register-org:
	@test -n "$(AIDBOX_SECRET)" || (echo "AIDBOX_SECRET is not set (check .env)" >&2 && exit 1)
	@test -f "$(ORGANIZATION)" || (echo "$(ORGANIZATION) not found - run 'make sushi-build' first" >&2 && exit 1)
	curl -sf -X PUT "http://$(AIDBOX_HOST):$(AIDBOX_PORT)/fhir/Organization/viome-document-intelligence-organization" \
		-H "Content-Type: application/json" \
		-u "root:$(AIDBOX_SECRET)" \
		-d @$(ORGANIZATION) \
		&& echo "\nRegistered viome-document-intelligence Organization with Aidbox at $(AIDBOX_HOST):$(AIDBOX_PORT)"
