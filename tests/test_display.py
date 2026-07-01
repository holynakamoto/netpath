from netpath.display import clean_asn_name


def test_clean_asn_name_exact_duplicate():
    """Exact duplicate around ' - ' is collapsed to a single occurrence."""
    assert clean_asn_name("Dimension Data - Dimension Data") == "Dimension Data"


def test_clean_asn_name_multi_word_exact_duplicate():
    """Multi-word exact duplicate is handled correctly."""
    assert clean_asn_name("Acme Corp - Acme Corp") == "Acme Corp"


def test_clean_asn_name_short_code_preserved():
    """Existing short-code stripping behavior is unaffected."""
    assert clean_asn_name("PARTNER-AS - Partner Comms") == "Partner Comms"
