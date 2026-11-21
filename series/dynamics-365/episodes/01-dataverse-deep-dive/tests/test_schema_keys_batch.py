"""Pure tests: table definitions, alternate-key URL segments, $batch bodies. No HTTP at all."""
import json
from datetime import date

import pytest

from dvlab import schema
from dvlab.batch import BatchItem, build_batch, parse_batch_response
from dvlab.keys import KeyValueError, UNSUPPORTED_KEY_CHARS, key_segment


# ---------- schema ----------
def test_table_has_exactly_one_primary_name_column_with_text_format():
    t = schema.project_request_table()
    primary = [a for a in t["Attributes"] if a.get("IsPrimaryName")]
    assert len(primary) == 1
    assert primary[0]["FormatName"] == {"Value": "Text"}
    assert t["OwnershipType"] == "UserOwned"
    for required in ("SchemaName", "DisplayName", "DisplayCollectionName", "IsActivity", "HasActivities", "HasNotes"):
        assert required in t


def test_every_schema_name_uses_the_publisher_prefix():
    names = [schema.project_request_table()["SchemaName"]] + [c["SchemaName"] for c in schema.extra_columns()]
    names += [schema.account_relationship()["SchemaName"], schema.account_relationship()["Lookup"]["SchemaName"],
              schema.request_code_key()["SchemaName"]]
    assert all(n.startswith(schema.PREFIX + "_") for n in names), names


def test_alternate_key_columns_exist_and_are_a_supported_type():
    cols = {c["SchemaName"].lower(): c for c in schema.extra_columns()}
    for k in schema.request_code_key()["KeyAttributes"]:
        assert k in cols
        assert cols[k]["@odata.type"].endswith("StringAttributeMetadata")   # string/int/decimal/date/lookup/choice only


def test_due_date_is_date_only_in_format_and_behavior():
    col = next(c for c in schema.extra_columns() if c["SchemaName"] == f"{schema.PREFIX}_DueDate")
    assert col["@odata.type"].endswith("DateTimeAttributeMetadata")
    assert col["Format"] == "DateOnly"
    # without this the column defaults to UserLocal and dates shift a day for users east of UTC (episode 5)
    assert col["DateTimeBehavior"] == {"Value": "DateOnly"}


def test_every_date_column_sets_a_behavior_that_fits_its_format():
    for c in schema.extra_columns():
        if c["AttributeType"] != "DateTime":
            continue
        assert "DateTimeBehavior" in c, c["SchemaName"]
        if c["DateTimeBehavior"]["Value"] == "DateOnly":
            assert c["Format"] == "DateOnly", c["SchemaName"]   # Learn: DateOnly behavior can't use DateAndTime format


def test_labels_only_set_localized_labels():
    blob = json.dumps([schema.project_request_table(), schema.extra_columns(), schema.account_relationship()])
    assert "UserLocalizedLabel" not in blob
    assert '"LanguageCode": 1033' in blob


def test_choice_values_use_the_option_value_prefix():
    choice = next(c for c in schema.extra_columns() if c["AttributeType"] == "Picklist")
    values = [o["Value"] for o in choice["OptionSet"]["Options"]]
    assert values == [727000000, 727000001, 727000002]
    assert choice["OptionSet"]["IsGlobal"] is False


def test_relationship_is_typed_and_removes_the_link_on_delete():
    rel = schema.account_relationship()
    assert rel["@odata.type"] == "Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata"
    assert rel["ReferencedEntity"] == "account" and rel["ReferencingEntity"] == schema.TABLE
    assert rel["CascadeConfiguration"]["Delete"] == "RemoveLink"
    assert rel["Lookup"]["AttributeType"] == "Lookup"


# ---------- alternate keys ----------
def test_key_segment_quotes_strings_and_doubles_inner_quotes():
    assert key_segment({"mgl_requestcode": "PR-0001"}) == "(mgl_requestcode='PR-0001')"
    assert key_segment({"name": "O'Brien"}) == "(name='O''Brien')"


def test_multi_part_key_keeps_order_and_types():
    seg = key_segment({"example_key1": 2, "example_key2": date(2027, 1, 31)})
    assert seg == "(example_key1=2,example_key2=2027-01-31)"


@pytest.mark.parametrize("ch", sorted(UNSUPPORTED_KEY_CHARS))
def test_values_with_unsupported_characters_are_rejected_before_sending(ch):
    with pytest.raises(KeyValueError):
        key_segment({"mgl_requestcode": f"PR{ch}0019"})


def test_empty_key_and_boolean_key_are_rejected():
    with pytest.raises(KeyValueError):
        key_segment({})
    with pytest.raises(KeyValueError):
        key_segment({"flag": True})


# ---------- $batch ----------
def test_batch_uses_crlf_and_numbers_content_ids_in_a_changeset():
    ct, body = build_batch([BatchItem("PATCH", "a(x='1')", {"n": 1}), BatchItem("PATCH", "a(x='2')", {"n": 2})],
                           "https://org/api/data/v9.2", boundary="batch_test")
    assert ct == 'multipart/mixed; boundary="batch_test"'
    assert "\r\n" in body and "\n" not in body.replace("\r\n", "")
    assert "Content-ID: 1" in body and "Content-ID: 2" in body
    assert "PATCH https://org/api/data/v9.2/a(x='1') HTTP/1.1" in body
    assert body.rstrip().endswith("--batch_test--")


def test_batch_limits_are_enforced():
    with pytest.raises(ValueError, match="1000"):
        build_batch([BatchItem("PATCH", f"a({i})", {}) for i in range(1001)], "https://org/api/data/v9.2")
    with pytest.raises(ValueError, match="GET"):
        build_batch([BatchItem("GET", "accounts")], "https://org/api/data/v9.2", changeset=True)
    build_batch([BatchItem("GET", "accounts")], "https://org/api/data/v9.2", changeset=False)  # fine outside one


def test_parse_batch_response_flattens_change_sets():
    text = (
        "--batchresponse_1\r\n"
        "Content-Type: multipart/mixed; boundary=changesetresponse_2\r\n\r\n"
        "--changesetresponse_2\r\nContent-Type: application/http\r\nContent-Transfer-Encoding: binary\r\n"
        "Content-ID: 1\r\n\r\nHTTP/1.1 204 No Content\r\nOData-Version: 4.0\r\n"
        "OData-EntityId: https://org/api/data/v9.2/tasks(00000000-0000-0000-0000-000000000001)\r\n\r\n\r\n"
        "--changesetresponse_2--\r\n"
        "--batchresponse_1\r\nContent-Type: application/http\r\nContent-Transfer-Encoding: binary\r\n\r\n"
        "HTTP/1.1 200 OK\r\nContent-Type: application/json; odata.metadata=minimal\r\n\r\n"
        '{"value":[{"subject":"Task 1"}]}\r\n'
        "--batchresponse_1--\r\n"
    )
    results = parse_batch_response("multipart/mixed; boundary=batchresponse_1", text)
    assert [r.status for r in results] == [204, 200]
    assert results[0].headers["OData-EntityId"].endswith("(00000000-0000-0000-0000-000000000001)")
    assert results[1].body == {"value": [{"subject": "Task 1"}]}
