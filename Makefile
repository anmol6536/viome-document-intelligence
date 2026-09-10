ifneq (,$(wildcard .env))
include .env
export
endif

AIDBOX_HOST ?= localhost
AIDBOX_PORT ?= 8080

STRUCTURE_DEFINITION := fhir-ig/fsh-generated/resources/StructureDefinition-viome-lab-observation.json

.PHONY: init sushi-build aidbox-register

## init: build the FHIR profile with SUSHI and register it with Aidbox
init: sushi-build aidbox-register

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
