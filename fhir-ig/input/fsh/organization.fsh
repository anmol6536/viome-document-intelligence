Instance: ViomeDocumentIntelligenceOrganization
InstanceOf: Organization
Usage: #definition
Title: "Viome Document Intelligence Organization"
Description: "Source Organization (Viome, the company) for the viome-document-intelligence EHR provider, resolved by the gateway's ingest pipeline (X-EHR-Provider -> Provider enum -> Organization lookup) so ingested resources can be tagged with Provenance.entity and provider-scoped dedup can work. Organization represents the owning entity (Viome); the Provider enum value stays scoped to this specific pipeline, so a future second Viome-owned provider could point at this same Organization or its own."

// BEST GUESS - not yet confirmed against the gateway's actual lookup
// query. If the gateway still can't resolve this provider after
// registering it, check what field/value it actually searches on
// (identifier system+value here is the most common pattern, but it
// may key on something else e.g. Organization.id itself).
* id = "viome-document-intelligence-organization"
* identifier[0].system = "http://viome.com/fhir/providers/viome-document-intelligence"
* identifier[0].value = "viome-document-intelligence"
* name = "Viome"
* active = true
