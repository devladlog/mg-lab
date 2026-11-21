"""What each format renders for fictional rows on 1 December 2026, 09:00 UTC."""
import json

from formatlint.__main__ import main, preview
from formatlint.expr import Context, evaluate, parse_excel
from formatlint.render import classes, render_column, render_view, texts
from conftest import SRC

OPEN = ["LinkTitle", "RequestStatus", "Requester", "Department", "Amount", "DueDate"]


def only(row, fields=OPEN):
    return {k: v for k, v in row.items() if k in fields}


def col(formats, name, field, row, sample):
    return render_column(formats[name], field, only(row), me=sample["me"], now=sample["now"],
                         display=row.get("__display", {}))


def test_status_pill_classes(formats, sample):
    expected = {"Laptop": "sp-field-severity--good", "Conference tickets": "sp-field-severity--low",
                "Office chairs": "sp-field-severity--good", "Software licence": "ms-fontColor-neutralSecondary",
                "Training course": "sp-field-severity--blocked"}
    for key, cls in expected.items():
        node = col(formats, "status.column.json", "RequestStatus", sample["rows"][key], sample)
        assert classes(node) == {cls}
        assert texts(node) == [sample["rows"][key]["RequestStatus"]]


def test_status_icons(formats, sample):
    icon = lambda k: col(formats, "status.column.json", "RequestStatus", sample["rows"][k], sample)["children"][0]["attrs"]["iconName"]
    assert icon("Training course") == "ErrorBadge"
    assert icon("Conference tickets") == "Forward"
    assert icon("Laptop") == "CheckMark"


def test_overdue_is_red_bold_with_icon(formats, sample):
    node = col(formats, "due-date.column.json", "DueDate", sample["rows"]["Laptop"], sample)   # due 28 Nov
    assert node["style"] == {"color": "#a4262c", "font-weight": "600"}
    assert node["children"][0]["attrs"]["iconName"] == "Warning"
    assert texts(node) == ["28/11/2026"]


def test_due_today_is_due_soon_not_overdue(formats, sample):
    node = col(formats, "due-date.column.json", "DueDate", sample["rows"]["Conference tickets"], sample)  # due 1 Dec
    assert node["style"]["color"] == "#8a6100"
    assert node["children"][0]["attrs"]["iconName"] == ""


def test_the_naive_comparison_flags_due_today_as_overdue(sample):
    # Learn's simple sample: [$DueDate] <= @now. A date-only value is midnight, so at 09:00 it's already "past".
    row = only(sample["rows"]["Conference tickets"])
    naive = evaluate(parse_excel("=if([$DueDate] <= @now, '#ff0000', '')"), Context(row=row, now=sample["now"]))
    assert naive == "#ff0000"


def test_closed_rejected_and_empty_dates_stay_plain(formats, sample):
    for key in ("Software licence", "Training course"):
        node = col(formats, "due-date.column.json", "DueDate", sample["rows"][key], sample)
        assert node["style"] == {"color": "", "font-weight": "400"}


def test_far_future_date_is_plain(formats, sample):
    node = col(formats, "due-date.column.json", "DueDate", sample["rows"]["Headsets"], sample)  # due 20 Dec
    assert node["style"]["color"] == ""


def test_amount_bar_width_and_cap(formats, sample):
    width = lambda k: col(formats, "amount.column.json", "Amount", sample["rows"][k], sample)["style"]["width"]
    assert width("Conference tickets") == "19.2%"          # 4,800 / 25,000
    assert width("Software licence") == "100%"             # capped
    node = col(formats, "amount.column.json", "Amount", sample["rows"]["Office chairs"], sample)
    assert node["attrs"]["title"] == "Needs director approval"
    assert texts(node) == ["€18,250.50"]


def test_requester_is_bold_for_me(formats, sample):
    mine = col(formats, "requester.column.json", "Requester", sample["rows"]["Laptop"], sample)
    other = col(formats, "requester.column.json", "Requester", sample["rows"]["Headsets"], sample)
    assert mine["style"]["font-weight"] == "600" and mine["text"] == "Alex Demo"
    assert other["style"]["font-weight"] == "400" and classes(other) == {"ms-fontColor-neutralSecondary"}


def test_row_class_only_for_open_overdue_items(formats, sample):
    got = {k: render_view(formats["open-requests.view.json"], only(r), now=sample["now"])["additionalRowClass"]
           for k, r in sample["rows"].items()}
    assert got == {"Laptop": "sp-field-severity--severeWarning", "Conference tickets": "", "Office chairs": "",
                   "Software licence": "", "Training course": "", "Headsets": ""}


def test_preview_of_a_view_without_requester():
    lines = preview(SRC / "formats" / "map.json", SRC / "sample-rows.json", "My open requests")
    assert len(lines) == 6
    assert all("Requester" not in line for line in lines)
    assert lines[0]["DueDate"] == "28/11/2026 | color:#a4262c"


def test_preview_cli_runs(capsys):
    assert main(["preview", str(SRC / "formats" / "map.json"), str(SRC / "sample-rows.json")]) == 0
    out = capsys.readouterr().out
    assert "Preview of view 'Open requests'" in out
    assert "row class      sp-field-severity--severeWarning" in out
