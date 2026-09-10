Profile: ViomeLabObservation
Parent: Observation
Id: viome-lab-observation
Title: "Viome Lab Observation"
Description: "A single lab result extracted from an uploaded report, scoped to Viome's document intelligence pipeline."

* status = #final (exactly)
* code 1..1 MS
* code.coding 1..* MS
* code.coding.system 1..1 MS
* code.coding.code 1..1 MS
* subject 1..1 MS
* subject.reference 1..1
* subject.reference obeys viome-subject-is-patient-reference
* effectiveDateTime 1..1 MS
* value[x] 1..1 MS
* valueQuantity only Quantity
* valueQuantity.value 1..1
* valueQuantity.unit 1..1
* valueQuantity.system 1..1
* valueQuantity.code 1..1

Invariant: viome-subject-is-patient-reference
Description: "Observation.subject.reference must point at a Patient resource."
Expression: "startsWith('Patient/')"
Severity: #error
