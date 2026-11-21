"""Acceptance tests for the copilot capability (Output parsing)."""
from logsub.copilot.parsing import parse
from logsub.schema import Label, Task


def test_output_parsing_both_labels_present():
    """Scenario: Both labels present"""
    # breaks if: the label is chosen by priority (MALICIOUS first) instead of first occurrence
    assert parse(Task.CLASSIFY, "BENIGN. Nothing malicious here.").label == Label.BENIGN


def test_output_parsing_leading_malicious_label_wins():
    """Scenario: Leading malicious label wins"""
    # breaks if: a later label overrides the first, or a "not" anywhere flips the result
    assert parse(Task.CLASSIFY, "MALICIOUS. This is not benign.").label == Label.MALICIOUS


def test_output_parsing_negated_label_is_skipped():
    """Scenario: Negated label is skipped"""
    # breaks if: negated labels are not skipped
    assert parse(Task.CLASSIFY, "Not malicious. BENIGN.").label == Label.BENIGN


def test_output_parsing_prefixed_label_is_not_a_whole_word():
    """Scenario: Prefixed label is not a whole word"""
    # breaks if: NON- prefixed labels are treated as plain labels
    assert parse(Task.CLASSIFY, "NON-MALICIOUS traffic, BENIGN").label == Label.BENIGN


def test_output_parsing_only_negated_labels():
    """Scenario: Only negated labels"""
    # breaks if: a negated label is still returned (or inverted into the opposite label)
    assert parse(Task.CLASSIFY, "Not malicious.").label is None


def test_output_parsing_case_insensitive_match():
    """Scenario: Case-insensitive match"""
    # breaks if: matching becomes case-sensitive
    assert parse(Task.CLASSIFY, "benign").label == Label.BENIGN


def test_output_parsing_unparseable_classification():
    """Scenario: Unparseable classification"""
    # breaks if: a default label is returned when neither word is present
    assert parse(Task.CLASSIFY, "I cannot determine this.").label is None


def test_output_parsing_remediation_without_a_clear_answer():
    """Scenario: Remediation without a clear answer"""
    # breaks if: action is recommended by default when no marker is present
    assert parse(Task.REMEDIATE, "Unclear.").recommends_action is False
