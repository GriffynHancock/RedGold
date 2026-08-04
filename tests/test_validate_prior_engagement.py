"""Build order step 5 acceptance test.

Acceptance criterion (§17.2): "Runs against [the prior engagement's] five phase*.json files and
correctly flags their known gaps."

The word doing the work is **correctly**. A validator that rejects every record because the schema
changed has not flagged a gap -- it has flagged a schema change, loudly, while staying silent on
everything that actually mattered. The first version of this validator did exactly that: 422
complaints, 67 of them about identifier format, and *zero* on verification, because the rules key
off a `finding_class` field those records do not carry.

So these tests assert named defects in named records, not counts.

The corpus lives outside this repo (client data never enters it), so every test skips cleanly if
it is not present. Point `RG_PRIOR_CORPUS` at the corpus directory to run this class locally,
e.g. `RG_PRIOR_CORPUS=~/engagements/<engagement-dir> python3 -m unittest discover -s tests`.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import findings as findings_mod  # noqa: E402

_CORPUS_ENV = os.environ.get("RG_PRIOR_CORPUS")
CORPUS = Path(_CORPUS_ENV).expanduser() if _CORPUS_ENV else None
PHASE_FILES = [
    "phase1b_osint_enum.json",
    "phase2_assets.json",
    "phase2b_access_control.json",
    "phase2c_deep_tests.json",
    "phase3_risks.json",
]


def corpus_available() -> bool:
    if CORPUS is None:
        return False
    return CORPUS.is_dir() and all((CORPUS / name).is_file() for name in PHASE_FILES)


@unittest.skipUnless(
    corpus_available(),
    "RG_PRIOR_CORPUS not set or corpus not present -- set it to a directory containing the "
    "phase*.json files to run this class",
)
class TestPriorEngagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = []
        cls.results = []
        cls.errors = []
        for name in PHASE_FILES:
            path = CORPUS / name
            records, errors = findings_mod.load_records(path, legacy=True)
            results, more_errors = findings_mod.validate_file(path, CORPUS, legacy=True)
            cls.records.extend(records)
            cls.results.extend(results)
            cls.errors.extend(errors + more_errors)
        cls.corpus_violations = findings_mod.validate_corpus(cls.records)
        cls.by_record: dict[str, set[str]] = {}
        for result in cls.results:
            cls.by_record.setdefault(result.record_id, set()).update(
                v.code for v in result.violations)
        for violation in cls.corpus_violations:
            cls.by_record.setdefault(violation.record_id, set()).add(violation.code)

    # --- the corpus parses at all ----------------------------------------------------------

    def test_all_five_files_parse(self):
        self.assertEqual(self.errors, [], "every phase file must be readable")

    def test_all_records_are_seen(self):
        self.assertEqual(len(self.results), 67, "the corpus is 67 records across five files")

    # --- gap 1: no finding was ever independently verified ---------------------------------

    def test_no_record_carries_independent_verification(self):
        """The headline gap. That engagement had no re-execution step at all."""
        verified = [r for r in self.records
                    if r.get("verified") in findings_mod.VERIFIED_STRONG]
        self.assertEqual(
            verified, [],
            "if any record now claims replayed/executed, the normaliser is laundering the gap",
        )

    def test_above_low_findings_are_flagged_as_unverified(self):
        flagged = [rid for rid, codes in self.by_record.items()
                   if "UNVERIFIED_ABOVE_LOW" in codes]
        self.assertTrue(
            flagged,
            "medium/high findings with no verification must be flagged -- this is the rule that "
            "would have caught an unproven claim reaching a client",
        )

    def test_proven_records_without_verification_are_flagged(self):
        flagged = [rid for rid, codes in self.by_record.items()
                   if "PROVEN_UNVERIFIED" in codes]
        self.assertTrue(flagged, "PROVEN with no re-execution is the central gap")

    # --- gap 2: decorative evidence anchors -------------------------------------------------

    def test_evidence_anchors_do_not_resolve(self):
        """Every evidence FILE exists; the #anchor fragments are informal prose.

        This is precisely §10.2's complaint: a human citation no script can check. A naive
        file-exists check reports the corpus clean.
        """
        unresolved = [rid for rid, codes in self.by_record.items()
                      if "EVIDENCE_UNRESOLVED" in codes]
        self.assertTrue(unresolved, "unresolvable anchors must be flagged")

    def test_prose_citations_are_flagged_as_uncheckable(self):
        """Several pointers are semicolon-separated citations with inline commentary."""
        flagged = [rid for rid, codes in self.by_record.items()
                   if "EVIDENCE_NOT_CHECKABLE" in codes]
        self.assertTrue(flagged, "prose citations must be distinguished from missing evidence")

    def test_the_evidence_itself_actually_exists(self):
        """The defect is the format, not absent evidence -- and saying so precisely matters.

        Hand-parsing the prose (split on ';', strip parenthetical commentary, drop the anchor)
        yields file paths that all exist. So the correct finding is "this pointer is not
        machine-checkable", never "the evidence is missing". Getting that distinction wrong
        would tell a client their engagement had no evidence, which is false and unfair.
        """
        import re

        hostname = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$", re.IGNORECASE)
        missing: list[str] = []
        for record in self.records:
            pointer = record.get("evidence_ptr")
            if not isinstance(pointer, str) or not pointer.strip():
                continue
            # Strip parenthetical commentary first -- it contains its own semicolons, so
            # splitting before stripping shreds the citation.
            cleaned = re.sub(r"\([^()]*\)", " ", pointer)
            for citation in cleaned.split(";"):
                path_part = citation.split("#")[0].strip()
                if not path_part:
                    continue
                # External URL citations are legitimate references, not local evidence files.
                if "://" in path_part or hostname.match(path_part.split("/")[0]):
                    continue
                if not (CORPUS / path_part).exists():
                    missing.append(f"{record.get('id')}: {path_part}")
        self.assertEqual(missing, [], "every cited local evidence file exists once prose is parsed")

    def test_the_prose_format_defeats_a_careful_parser(self):
        """Why EVIDENCE_NOT_CHECKABLE is the right verdict rather than a stricter regex.

        Reconstructing these pointers took: strip balanced parentheticals (they contain their own
        semicolons), split on the remainder, drop the anchor, then distinguish external URL
        citations from local paths. That is a bespoke parser for one engagement's habits -- which
        is the argument for a format the tool controls, not a smarter reader.
        """
        import re

        awkward = [
            r.get("id") for r in self.records
            if isinstance(r.get("evidence_ptr"), str)
            and re.search(r"\([^()]*;[^()]*\)", r["evidence_ptr"])
        ]
        self.assertTrue(
            awkward,
            "at least one pointer nests a semicolon inside commentary -- the case that breaks "
            "the obvious split-on-semicolon parse",
        )

    # --- gap 3: stale records the engagement had already resolved ---------------------------

    def test_r004_is_flagged_as_superseded(self):
        """F-C002 states it resolves R-004, but R-004 still reads SPECULATED."""
        self.assertIn("STALE_SUPERSEDED", self.by_record.get("R-004", set()))

    def test_r009_is_flagged_as_superseded(self):
        """F-C001 states it resolves R-009 as a clean negative; R-009 still reads SPECULATED."""
        self.assertIn("STALE_SUPERSEDED", self.by_record.get("R-009", set()))

    def test_supersession_message_names_the_resolving_record(self):
        stale = [v for v in self.corpus_violations
                 if v.code == "STALE_SUPERSEDED" and v.record_id == "R-004"]
        self.assertTrue(stale)
        self.assertIn("F-C002", stale[0].message)

    # --- gap 4: self-contradiction ----------------------------------------------------------

    def test_r004_is_flagged_as_speculated_yet_above_low(self):
        """The corpus's only SPECULATED record carrying a medium severity."""
        self.assertIn("SPECULATED_ABOVE_LOW", self.by_record.get("R-004", set()))

    # --- gap 5: rollup double-counting ------------------------------------------------------

    def test_synthesis_records_are_flagged_as_rollups(self):
        rollups = [v.record_id for v in self.corpus_violations if v.code == "ROLLUP"]
        self.assertTrue(
            rollups,
            "phase3 records synthesise earlier ones; naive concatenation double-counts them",
        )

    def test_rollup_is_advisory_not_blocking(self):
        # A rollup is a reporting concern, not a defect in the finding itself.
        for violation in self.corpus_violations:
            if violation.code == "ROLLUP":
                self.assertFalse(violation.blocking)

    # --- the noise floor --------------------------------------------------------------------

    def test_identifier_convention_is_not_treated_as_a_defect(self):
        """The regression that motivated this file.

        Legacy identifiers (R-004, P2-016, F-C001) predate the F-NNN convention. Flagging all 67
        buried the real findings.
        """
        bad_ids = [rid for rid, codes in self.by_record.items() if "BAD_ID" in codes]
        self.assertEqual(bad_ids, [], "legacy identifiers must not be reported as defects")

    def test_severity_positive_is_understood_not_rejected(self):
        """`positive` recorded a control that held -- a first-class result, not a bad enum."""
        bad_enum_severity = [
            r.record_id for r in self.results
            for v in r.violations
            if v.code == "BAD_ENUM" and "severity" in v.message
        ]
        self.assertEqual(bad_enum_severity, [])

    def test_confidence_vocabulary_is_mapped_not_rejected(self):
        bad_enum_confidence = [
            r.record_id for r in self.results
            for v in r.violations
            if v.code == "BAD_ENUM" and "confidence" in v.message
        ]
        self.assertEqual(bad_enum_confidence, [])


if __name__ == "__main__":
    unittest.main()
