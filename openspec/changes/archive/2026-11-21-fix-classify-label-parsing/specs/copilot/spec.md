# Spec Delta

## MODIFIED Requirements

### Requirement: Output parsing

Raw model output SHALL be parsed into a decision. For `classify`, the label is the first
whole-word MALICIOUS or BENIGN (case-insensitive) not directly preceded by NOT or NON-; negated
labels are skipped, and if none remains the label is absent. For `summarize`, the summary is the
trimmed text. For `remediate`, action is recommended only if the text contains `ACTION:` and not
`NO ACTION`.

#### Scenario: Both labels present
- **WHEN** a classify answer is "BENIGN. Nothing malicious here."
- **THEN** the parsed label is benign

#### Scenario: Leading malicious label wins
- **WHEN** a classify answer is "MALICIOUS. This is not benign."
- **THEN** the parsed label is malicious

#### Scenario: Negated label is skipped
- **WHEN** a classify answer is "Not malicious. BENIGN."
- **THEN** the parsed label is benign

#### Scenario: Prefixed label is not a whole word
- **WHEN** a classify answer is "NON-MALICIOUS traffic, BENIGN"
- **THEN** the parsed label is benign

#### Scenario: Only negated labels
- **WHEN** a classify answer is "Not malicious."
- **THEN** the parsed label is absent

#### Scenario: Case-insensitive match
- **WHEN** a classify answer is "benign"
- **THEN** the parsed label is benign

#### Scenario: Unparseable classification
- **WHEN** a classify answer contains neither word
- **THEN** the parsed label is absent

#### Scenario: Remediation without a clear answer
- **WHEN** a remediate answer contains neither `ACTION:` nor `NO ACTION`
- **THEN** the decision is that no action is recommended
