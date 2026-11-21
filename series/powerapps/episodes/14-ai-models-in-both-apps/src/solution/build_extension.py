#!/usr/bin/env python3
"""Build the ContosoInspectionsAI extension solution (export format) next to the ep 12 base schema.

  python build_extension.py --out ContosoInspectionsAI            # writes Other/Solution.xml + Other/Customizations.xml style export files
  python build_extension.py --zip /tmp/cin-ai.zip                 # export-format zip, ready for `pac solution unpack`

It reuses attribute_xml() from episode 12's build_solution.py (read-only, never edited) so the column XML cannot drift
from the base. Nothing here talks to a tenant.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EP = HERE.parents[2]
BASE_SCRIPT = EP / "12-build-a-model-driven-app-from-start-to-end" / "src" / "schema" / "build_solution.py"
BASE_SCHEMA = HERE.parent / "schema" / "contosoinspections.schema.json"
EXT = HERE / "extension.schema.json"


def load_base():
    spec = importlib.util.spec_from_file_location("ep12_build_solution", BASE_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def check_extension(base_schema, ext):
    """New columns only: none may exist in the base, and every table must be a base table."""
    base = {t["logicalName"]: {c["logicalName"] for c in t["columns"]} | {t["primaryName"]["logicalName"]} for t in base_schema["tables"]}
    for t in ext["tables"]:
        if t["logicalName"] not in base:
            raise ValueError(f"unknown base table {t['logicalName']}")
        for c in t["columns"]:
            if c["logicalName"] in base[t["logicalName"]]:
                raise ValueError(f"{c['logicalName']} already exists in the base schema")
            if not c["logicalName"].startswith(base_schema["publisher"]["prefix"] + "_"):
                raise ValueError(f"{c['logicalName']} does not use the publisher prefix")


def build(base_schema, ext):
    check_extension(base_schema, ext)
    b = load_base()
    m = b.Model(base_schema)
    ents = []
    for t in ext["tables"]:
        ln = t["logicalName"]
        base_t = m.tables[ln]
        attrs = "".join(b.attribute_xml(m, ln, c).replace(
            f'<Description description="" languagecode="{b.LCID}" />', f'<Description description={b.q(c.get("description", ""))} languagecode="{b.LCID}" />')
            for c in t["columns"])
        ents.append(f"""    <Entity>
      <Name LocalizedName={b.q(base_t['displayName'])} OriginalName={b.q(base_t['displayName'])}>{ln}</Name>
      <EntityInfo>
        <entity Name="{ln}">
          <attributes>
{attrs}          </attributes>
        </entity>
      </EntityInfo>
    </Entity>
""")
    s = ext["solution"]
    p = base_schema["publisher"]
    roots = "\n".join(f'      <RootComponent type="1" schemaName="{t["logicalName"]}" behavior="1" />' for t in ext["tables"])
    # behavior="1" = "Include subcomponents": only the attributes listed in customizations.xml travel, not the whole table.
    solution = f"""<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml version="9.2.0.0" SolutionPackageVersion="9.2" languagecode="{b.LCID}" generatedBy="CrmLive" {b.XSI}>
  <SolutionManifest>
    <UniqueName>{s['uniqueName']}</UniqueName>
    <LocalizedNames>
      <LocalizedName description={b.q(s['displayName'])} languagecode="{b.LCID}" />
    </LocalizedNames>
    <Descriptions>
      <Description description={b.q(s['description'])} languagecode="{b.LCID}" />
    </Descriptions>
    <Version>{s['version']}</Version>
    <Managed>0</Managed>
    <Publisher>
      <UniqueName>{p['uniqueName']}</UniqueName>
      <LocalizedNames>
        <LocalizedName description={b.q(p['displayName'])} languagecode="{b.LCID}" />
      </LocalizedNames>
      <Descriptions>
        <Description description={b.q(p['description'])} languagecode="{b.LCID}" />
      </Descriptions>
      <EMailAddress xsi:nil="true"></EMailAddress>
      <SupportingWebsiteUrl xsi:nil="true"></SupportingWebsiteUrl>
      <CustomizationPrefix>{p['prefix']}</CustomizationPrefix>
      <CustomizationOptionValuePrefix>{p['optionValuePrefix']}</CustomizationOptionValuePrefix>
      <Addresses>
        <Address><AddressNumber>1</AddressNumber><AddressTypeCode>1</AddressTypeCode><ShippingMethodCode>1</ShippingMethodCode></Address>
        <Address><AddressNumber>2</AddressNumber><AddressTypeCode>1</AddressTypeCode><ShippingMethodCode>1</ShippingMethodCode></Address>
      </Addresses>
    </Publisher>
    <RootComponents>
{roots}
    </RootComponents>
    <MissingDependencies />
  </SolutionManifest>
</ImportExportXml>
"""
    custom = f"""<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml {b.XSI}>
  <Entities>
{"".join(ents)}  </Entities>
  <Roles></Roles>
  <Workflows />
  <FieldSecurityProfiles></FieldSecurityProfiles>
  <Templates />
  <EntityMaps />
  <EntityRelationships />
  <OrganizationSettings />
  <optionsets />
  <CustomControls />
  <EntityDataProviders />
  <Languages>
    <Language>{b.LCID}</Language>
  </Languages>
</ImportExportXml>
"""
    return {"solution.xml": solution, "customizations.xml": custom, "[Content_Types].xml": b.content_types()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", help="write an export-format zip")
    ap.add_argument("--out", help="write the three files into this folder")
    a = ap.parse_args(argv)
    files = build(json.loads(BASE_SCHEMA.read_text(encoding="utf-8")), json.loads(EXT.read_text(encoding="utf-8")))
    if a.zip:
        load_base().write_zip(files, a.zip)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for n, t in files.items():
            (out / n).write_text(t, encoding="utf-8")
    if not (a.zip or a.out):
        ap.error("give --zip and/or --out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
