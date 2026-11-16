# Spec Delta

## MODIFIED Requirements

### Requirement: Payloads never violate field constraints

A payload not marked infeasible SHALL fit the target field's constraint when appended to
the field's current value. Before checking fit, an arm SHALL adapt the candidate to the field's
character set: if the set forbids spaces, each space becomes the first admissible of `+`, `_`,
`-`, and any other inadmissible character is dropped. A too-long candidate SHALL be shortened to
its longest fitting prefix; if no non-empty text fits, the payload SHALL be marked infeasible.

#### Scenario: Over-long candidate is trimmed
- **WHEN** a candidate is longer than the room left in the target field
- **THEN** the payload text is the longest prefix of the candidate that fits

#### Scenario: Spaces adapted for a URL field
- **WHEN** a candidate containing spaces targets the nginx `uri` field
- **THEN** the payload text has `+` where the candidate had spaces

#### Scenario: Adapted for a username field
- **WHEN** a candidate containing spaces and a colon targets the ssh `user` field
- **THEN** the spaces become `_`, the colon is dropped, and only characters from `[A-Za-z0-9._-]` remain

#### Scenario: Applying a feasible payload
- **WHEN** a feasible payload is applied to its record
- **THEN** an injected record is returned without a constraint violation

#### Scenario: Applying an infeasible payload
- **WHEN** an infeasible payload is applied to a record
- **THEN** the returned record is marked as injected by that arm but its field values are unchanged

### Requirement: Handwritten arm

The handwritten arm SHALL try the attack class's templates in order, each prefixed by a
space, adapted to the field's character set and appended to the field, and SHALL return the
first one that fits without trimming. Its budget used is the number of templates tried. If none
fits, the payload is infeasible.

#### Scenario: Roomy field
- **WHEN** the handwritten arm targets an nginx `user_agent` field
- **THEN** it returns the first template of the class with budget used 1

#### Scenario: Field that forbids spaces
- **WHEN** the handwritten arm targets the nginx `uri` field
- **THEN** it returns a feasible payload containing no spaces

#### Scenario: Field too short for every template
- **WHEN** the handwritten arm targets the ssh `user` field with attack class `A2`
- **THEN** the payload is infeasible, because no adapted template fits in 32 characters
