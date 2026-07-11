from unittest.mock import patch

from netpath import asn


def test_cymru_bulk_asn_lookup_parses_asn_records():
    response = (
        "Bulk mode; whois.cymru.com [2026-07-11 17:51:43 +0000]\n"
        "15169   | US | arin     | 2000-03-30 | GOOGLE - Google LLC, US\n"
        "38195   | AU | apnic    | 2006-08-09 | SUPERLOOP-AS-AP - Superloop, AU\n"
    )
    with patch("netpath.asn._cymru_query", return_value=response) as query:
        result = asn.cymru_bulk_asn_lookup(["AS15169", "38195"])

    assert query.call_args.args[0] == ["AS15169", "AS38195"]
    assert result["AS15169"] == {
        "country": "US",
        "registry": "arin",
        "name": "GOOGLE - Google LLC",
    }
    assert result["AS38195"]["country"] == "AU"


def test_cymru_bulk_asn_lookup_skips_unattributed_rows():
    response = (
        "Bulk mode; whois.cymru.com [2026-07-11 17:51:43 +0000]\n"
        "NA      | NA | NA       | NA         | NA\n"
    )
    with patch("netpath.asn._cymru_query", return_value=response):
        assert asn.cymru_bulk_asn_lookup(["AS64500"]) == {}


def test_cymru_bulk_asn_lookup_empty_input_makes_no_query():
    with patch("netpath.asn._cymru_query") as query:
        assert asn.cymru_bulk_asn_lookup([]) == {}
    query.assert_not_called()


def test_cymru_bulk_asn_lookup_returns_empty_on_persistent_failure():
    with patch("netpath.asn._cymru_query", side_effect=OSError("timeout")), \
         patch("netpath.asn.time.sleep"):
        import warnings as warnings_mod
        with warnings_mod.catch_warnings():
            warnings_mod.simplefilter("ignore")
            assert asn.cymru_bulk_asn_lookup(["AS15169"]) == {}
