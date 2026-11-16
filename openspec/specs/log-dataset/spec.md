# log-dataset Specification

## Purpose
Produce labeled, provenance-tagged Linux host log records for three log substrates, and
place attacker payloads into attacker-controlled fields while honoring each field's
length and character-set constraints.

## Requirements

### Requirement: Supported log substrates

The system SHALL support exactly three log substrates — `nginx_access`, `auditd_execve`
and `ssh_auth` — each with a fixed, ordered set of fields.

#### Scenario: nginx access record fields
- **WHEN** an `nginx_access` record is produced
- **THEN** it has the fields `remote_addr`, `time_local`, `method`, `uri`, `query`, `protocol`, `status`, `body_bytes`, `referer` and `user_agent`

#### Scenario: auditd execve record fields
- **WHEN** an `auditd_execve` record is produced
- **THEN** it has the fields `timestamp`, `pid`, `uid`, `exe`, `path` and `argv`

#### Scenario: ssh auth record fields
- **WHEN** an `ssh_auth` record is produced
- **THEN** it has the fields `timestamp`, `host`, `result`, `user`, `src_ip`, `port` and `client_version`

### Requirement: Per-field provenance

Every record SHALL tag each field as either `attacker_controlled` or `system_generated`.
The attacker-controlled fields are: `uri`, `query`, `referer`, `user_agent` (nginx);
`path`, `argv` (auditd); `user`, `client_version` (ssh). All other fields are
system-generated.

#### Scenario: Listing attacker-controlled fields
- **WHEN** the attacker-controlled fields of an `ssh_auth` record are requested
- **THEN** exactly `user` and `client_version` are returned

### Requirement: Field-constraint manifest

Each attacker-controlled field SHALL have a constraint consisting of a maximum length and
a named character set (`printable_ascii`, `url` or `username`). A value is admissible
only if it is no longer than the maximum and every character belongs to the character set.

#### Scenario: Manifest values
- **WHEN** the constraint manifest is read
- **THEN** it declares `user_agent` 512/`printable_ascii`; `uri`, `query`, `referer` 2048/`url`; `path` 4096/`url`; `argv` 4096/`printable_ascii`; `user` 32/`username`; `client_version` 255/`printable_ascii`

#### Scenario: Over-length value rejected
- **WHEN** a 33-character value is validated against the `user` field
- **THEN** validation fails with a reason stating the length exceeds the maximum

#### Scenario: Out-of-charset value rejected
- **WHEN** a value containing a space is validated against the `user` field
- **THEN** validation fails with a reason naming the `username` character set

### Requirement: Seeded synthetic generation

The system SHALL generate a requested number of clean (un-injected) records for a
substrate. Given the same substrate, count, malicious ratio and integer seed, generation
SHALL produce identical records, including record ids.

#### Scenario: Reproducible generation
- **WHEN** 50 `nginx_access` records are generated twice with seed 7
- **THEN** both runs produce identical records, field for field and id for id

#### Scenario: Generated records are clean
- **WHEN** records are generated for any substrate
- **THEN** no record carries an injection

### Requirement: Ground-truth labels

Every generated record SHALL carry a ground-truth label (`malicious` or `benign`) and an
attack type. Benign records have attack type `none`. Each record is malicious with
probability equal to the requested malicious ratio. Malicious attack types are drawn
per substrate: nginx from `sqli`, `command_injection`, `path_traversal`, `scanning`,
`credential_stuffing`; auditd from `command_injection`, `path_traversal`; ssh is always
`credential_stuffing`.

#### Scenario: All-malicious generation
- **WHEN** records are generated with a malicious ratio of 1.0
- **THEN** every record is labeled `malicious` with an attack type other than `none`

#### Scenario: All-benign generation
- **WHEN** records are generated with a malicious ratio of 0.0
- **THEN** every record is labeled `benign` with attack type `none`

### Requirement: Raw log line rendering

The system SHALL render a record's fields into a single representative raw log line in
its substrate's format, containing every field value verbatim. This line is the text the
copilot reads.

#### Scenario: Injected text reaches the rendered line
- **WHEN** an nginx record whose `user_agent` contains a payload is rendered
- **THEN** the rendered line contains the payload text verbatim

### Requirement: Constraint-enforcing injection

The system SHALL inject a payload into one attacker-controlled field of a record by
appending, prepending or replacing the field's value, and SHALL return a new record
that carries injection metadata (field, payload id, arm, attack class) and a new id.
The original record SHALL NOT be modified.

#### Scenario: Successful append injection
- **WHEN** a payload is injected into `user_agent` in append mode and the result fits the constraint
- **THEN** the new record's `user_agent` equals the original value followed by the payload, and its injection metadata names `user_agent`

#### Scenario: Original record preserved
- **WHEN** a payload is injected into a record
- **THEN** the original record's fields and injection (none) are unchanged

#### Scenario: Constraint violation rejected
- **WHEN** an injection would make the field value violate its constraint and enforcement is on
- **THEN** a constraint-violation error is raised and no record is returned

#### Scenario: Enforcement disabled
- **WHEN** an injection violates the field constraint but enforcement is off
- **THEN** the injected record is returned anyway

#### Scenario: System-generated field refused
- **WHEN** injection into a system-generated field such as `remote_addr` is requested
- **THEN** an error is raised stating the field is not attacker-controlled

### Requirement: Fit check

The system SHALL provide a non-raising check that reports whether a payload, placed in a
given field and mode, would satisfy that field's constraint. Fields without a constraint
SHALL report as not fitting.

#### Scenario: Fit check on a tight field
- **WHEN** a 40-character payload is checked against the `user` field
- **THEN** the check reports that it does not fit

### Requirement: Dataset generation command

The CLI SHALL provide a `gen` command taking a substrate, record count, malicious ratio
and optional seed, writing one JSON record per line to a given output file (creating
parent directories) or to standard output when no file is given.

#### Scenario: Writing to a file
- **WHEN** `logsub gen --substrate nginx_access --n 200 --out data/nginx.jsonl` is run
- **THEN** `data/nginx.jsonl` contains 200 JSON records, one per line, and a summary with the malicious count is printed to standard error

#### Scenario: Writing to standard output
- **WHEN** `logsub gen` is run without `--out`
- **THEN** the records are printed to standard output, one JSON record per line
