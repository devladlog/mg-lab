#!/usr/bin/env python3
"""Schema script for the ContosoInspections solution.

contosoinspections.schema.json  --(this script)-->  solution in export format (solution.xml + customizations.xml)
                                --(pac solution unpack)-->  src/solution  (the committed, diff-friendly source)

Usage:
  python build_solution.py --profile full  --out ../solution            # tables + the finished back-office app
  python build_solution.py --profile data  --out /tmp/data-only         # tables only (the starting point of the recording)
  python build_solution.py --profile full  --out ../solution --pac pac  # default: calls `pac solution unpack` (offline, no sign-in)
  python build_solution.py --profile full  --export-zip x.zip           # only write the export-format zip, no unpack

Everything is generated with deterministic GUIDs (uuid5), so re-running produces identical files.
Standard library only. Nothing here talks to a tenant: `pac solution unpack` / `pack` are offline.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "contosoinspections.schema.json"
NS = uuid.UUID("6f3a2c1e-0000-4000-8000-0c0a70500a12")
LCID = 1033
VERSION = "1.0.0.0"
XSI = 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'

# Control class ids (Learn: "Controls in model-driven apps" / classid reference)
CLASS = {
    "string": "{4273EDBD-AC1D-40d3-9FB2-095C621B552D}",
    "email": "{ADA2203E-B4CD-49be-9DDF-234642B43B52}",
    "phone": "{F3015350-44A2-4aa0-97B5-00166532B5E9}",
    "memo": "{E0DECE4B-6FC8-4a8f-A065-082708572369}",
    "bool": "{67FAC785-CD58-4F9F-ABB3-4B7DDC6ED5ED}",
    "whole": "{C6D124CA-7EDA-4A60-AEA9-7FB8D318B68F}",
    "date": "{5B773807-9FB2-42DB-97C3-7A91EFF8ADFF}",
    "choice": "{3EF39988-22BB-4F0B-BBBE-64B5A3748AEE}",
    "lookup": "{270BD3DB-D9AF-4782-9025-509E298DEC0A}",
    "owner": "{270BD3DB-D9AF-4782-9025-509E298DEC0A}",
    "subgrid": "{E7A81278-8635-4d9e-8D4D-59480B391C5B}",
}
PRIV_LEVEL = {"Basic": "Basic", "Local": "Local", "Deep": "Deep", "Global": "Global"}
BEHAVIOR = {"Restrict": ("Restrict", "NoCascade"), "RemoveLink": ("RemoveLink", "NoCascade"), "Cascade": ("Cascade", "Cascade")}


def gid(*parts):
    return "{" + str(uuid.uuid5(NS, "/".join(parts))).upper() + "}"


def q(s):
    return quoteattr(str(s))


def load(path=SCHEMA):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Model:
    """Convenience lookups over the schema."""

    def __init__(self, schema):
        self.s = schema
        self.prefix = schema["publisher"]["prefix"]
        self.tables = {t["logicalName"]: t for t in schema["tables"]}

    def column(self, table, logical):
        t = self.tables[table]
        if logical == t["primaryName"]["logicalName"]:
            return {"logicalName": logical, "displayName": t["primaryName"]["displayName"], "type": "string"}
        for c in t["columns"]:
            if c["logicalName"] == logical:
                return c
        if logical in ("ownerid", "createdon", "modifiedon", "statecode", "statuscode"):
            return {"logicalName": logical, "displayName": logical, "type": "owner" if logical == "ownerid" else "system"}
        raise KeyError(f"{table}.{logical}")

    def option_value(self, choice_name, value):
        return self.s["publisher"]["optionValuePrefix"] * 10000 + value

    def view_id(self, table, name):
        return gid("view", table, name)

    def chart_id(self, name):
        return gid("chart", name)

    def form_id(self, table, kind):
        return gid("form", table, kind)

    @property
    def dashboard_id(self):
        return gid("dashboard", self.s["ui"]["dashboard"]["name"])

    @property
    def sitemap_id(self):
        return gid("sitemap", self.s["ui"]["app"]["uniqueName"])

    @property
    def app_id(self):
        return gid("app", self.s["ui"]["app"]["uniqueName"])

    def role_id(self, name):
        return gid("role", name)

    def profile_id(self, name):
        return gid("fieldsecurityprofile", name)


def label(text):
    return f'<label description={q(text)} languagecode="{LCID}" />'


def names(tag, text):
    return f'<{tag}s><{tag} description={q(text)} languagecode="{LCID}" /></{tag}s>'


# ---------------------------------------------------------------- attributes
def common_attr(logical, display, typ, required="none", extra="", mask="ValidForAdvancedFind|ValidForForm|ValidForGrid", secured=False,
                description="", auto=""):
    return f"""        <attribute PhysicalName="{logical}">
          <Type>{typ}</Type>
          <Name>{logical}</Name>
          <LogicalName>{logical}</LogicalName>
          <RequiredLevel>{required}</RequiredLevel>
          <DisplayMask>{mask}</DisplayMask>
{extra}          <ValidForUpdateApi>1</ValidForUpdateApi>
          <ValidForReadApi>1</ValidForReadApi>
          <ValidForCreateApi>1</ValidForCreateApi>
          <IsCustomField>1</IsCustomField>
          <IsAuditEnabled>0</IsAuditEnabled>
          <IsSecured>{1 if secured else 0}</IsSecured>
          <IntroducedVersion>{VERSION}</IntroducedVersion>
          <IsCustomizable>1</IsCustomizable>
          <IsRenameable>1</IsRenameable>
          <CanModifySearchSettings>1</CanModifySearchSettings>
          <CanModifyRequirementLevelSettings>1</CanModifyRequirementLevelSettings>
          <CanModifyAdditionalSettings>1</CanModifyAdditionalSettings>
          <SourceType>0</SourceType>
          <IsGlobalFilterEnabled>0</IsGlobalFilterEnabled>
          <IsSortableEnabled>0</IsSortableEnabled>
          <CanModifyGlobalFilterSettings>1</CanModifyGlobalFilterSettings>
          <CanModifyIsSortableSettings>1</CanModifyIsSortableSettings>
          <IsDataSourceSecret>0</IsDataSourceSecret>
          <AutoNumberFormat>{escape(auto)}</AutoNumberFormat>
          <IsSearchable>0</IsSearchable>
          <IsFilterable>0</IsFilterable>
          <IsRetrievable>0</IsRetrievable>
          <IsLocalizable>0</IsLocalizable>
          <displaynames>
            <displayname description={q(display)} languagecode="{LCID}" />
          </displaynames>
          <Descriptions>
            <Description description={q(description)} languagecode="{LCID}" />
          </Descriptions>
        </attribute>
"""


def option_xml(m, table, col):
    opts = "".join(
        f'            <option value="{m.option_value(col["choice"], v)}" ExternalValue="" IsHidden="0"><labels>{label(text)}</labels></option>\n'
        for text, v in col["options"])
    return (f'          <optionset Name="{table}_{col["logicalName"]}">\n'
            f'            <OptionSetType>picklist</OptionSetType>\n'
            f'            <IsGlobal>0</IsGlobal>\n'
            f'            <IntroducedVersion>{VERSION}</IntroducedVersion>\n'
            f'            <IsCustomizable>1</IsCustomizable>\n'
            f'            <displaynames><displayname description={q(col["displayName"])} languagecode="{LCID}" /></displaynames>\n'
            f'            <Descriptions><Description description="" languagecode="{LCID}" /></Descriptions>\n'
            f'            <options>\n{opts}            </options>\n'
            f'          </optionset>\n')


def bool_xml(table, col):
    d = 1 if col.get("default") else 0
    return (f'          <optionset Name="{table}_{col["logicalName"]}">\n'
            f'            <OptionSetType>bool</OptionSetType>\n'
            f'            <IsGlobal>0</IsGlobal>\n'
            f'            <IntroducedVersion>{VERSION}</IntroducedVersion>\n'
            f'            <IsCustomizable>1</IsCustomizable>\n'
            f'            <displaynames><displayname description={q(col["displayName"])} languagecode="{LCID}" /></displaynames>\n'
            f'            <Descriptions><Description description="" languagecode="{LCID}" /></Descriptions>\n'
            f'            <options>\n'
            f'              <option value="1" ExternalValue="" IsHidden="0"><labels>{label("Yes")}</labels></option>\n'
            f'              <option value="0" ExternalValue="" IsHidden="0"><labels>{label("No")}</labels></option>\n'
            f'            </options>\n'
            f'          </optionset>\n'), d


def attribute_xml(m, table, col):
    n, disp = col["logicalName"], col["displayName"]
    req = "required" if col.get("required") else "none"
    secured = bool(col.get("secured"))
    t = col["type"]
    if t in ("string", "email", "phone"):
        fmt = {"string": "text", "email": "email", "phone": "phone"}[t]
        ml = col.get("maxLength", 100)
        extra = (f"          <Format>{fmt}</Format>\n          <MaxLength>{ml}</MaxLength>\n          <Length>{ml * 2}</Length>\n"
                 f"          <ImeMode>auto</ImeMode>\n")
        return common_attr(n, disp, "nvarchar", req, extra, secured=secured)
    if t == "memo":
        ml = col.get("maxLength", 2000)
        extra = f"          <Format>textarea</Format>\n          <MaxLength>{ml}</MaxLength>\n          <Length>{ml * 2}</Length>\n          <ImeMode>auto</ImeMode>\n"
        return common_attr(n, disp, "ntext", req, extra, secured=secured)
    if t == "whole":
        extra = (f"          <Format>none</Format>\n          <MinValue>{col.get('min', -2147483648)}</MinValue>\n"
                 f"          <MaxValue>{col.get('max', 2147483647)}</MaxValue>\n")
        return common_attr(n, disp, "int", req, extra, secured=secured)
    if t == "date":
        extra = ("          <Behavior>3</Behavior>\n          <CanChangeDateTimeBehavior>1</CanChangeDateTimeBehavior>\n"
                 "          <Format>date</Format>\n          <ImeMode>inactive</ImeMode>\n")
        return common_attr(n, disp, "datetime", req, extra, secured=secured)
    if t == "bool":
        opt, d = bool_xml(table, col)
        extra = f"          <DefaultValue>{d}</DefaultValue>\n{opt}"
        return common_attr(n, disp, "bit", req, extra, secured=secured)
    if t == "choice":
        dv = col.get("default", 0)
        extra = (f"          <DefaultFormValue>{m.option_value(col['choice'], dv)}</DefaultFormValue>\n"
                 f"{option_xml(m, table, col)}")
        return common_attr(n, disp, "picklist", req, extra, secured=secured)
    if t == "image":
        # Learn (create and edit columns, image columns): CanStoreFullImage keeps the full-size picture next to the thumbnail.
        extra = (f"          <MaxSizeInKB>{col.get('maxSizeKB', 10240)}</MaxSizeInKB>\n          <CanStoreFullImage>1</CanStoreFullImage>\n"
                 f"          <IsPrimaryImage>0</IsPrimaryImage>\n")
        return common_attr(n, disp, "image", req, extra, secured=secured)
    if t == "lookup":
        extra = "          <LookupStyle>single</LookupStyle>\n          <LookupTypes />\n"
        return common_attr(n, disp, "lookup", req, extra, secured=secured)
    raise ValueError(f"unknown column type {t}")


def entity_xml(m, t):
    ln = t["logicalName"]
    pn = t["primaryName"]
    pk = common_attr(f"{ln}id", t["displayName"], "primarykey", "systemrequired",
                     mask="ValidForAdvancedFind|RequiredForForm|ValidForForm|ValidForGrid",
                     description="Unique identifier for entity instances").replace("<IsCustomField>1", "<IsCustomField>0")
    ml = pn.get("maxLength", 100)
    name_attr = common_attr(pn["logicalName"], pn["displayName"], "nvarchar", "required",
                            f"          <Format>text</Format>\n          <MaxLength>{ml}</MaxLength>\n          <Length>{ml * 2}</Length>\n          <ImeMode>auto</ImeMode>\n",
                            mask="PrimaryName|ValidForAdvancedFind|ValidForForm|ValidForGrid|RequiredForForm",
                            description=f"The name of the custom entity.", auto=pn.get("autoNumber", ""))
    attrs = pk + name_attr + "".join(attribute_xml(m, ln, c) for c in t["columns"])
    own = "UserOwned" if t["ownership"] == "UserOwned" else "OrgOwned"
    qc = 1 if t.get("quickCreate") else 0
    return f"""    <Entity>
      <Name LocalizedName={q(t['displayName'])} OriginalName={q(t['displayName'])}>{ln}</Name>
      <EntityInfo>
        <entity Name="{ln}">
          <LocalizedNames>
            <LocalizedName description={q(t['displayName'])} languagecode="{LCID}" />
          </LocalizedNames>
          <LocalizedCollectionNames>
            <LocalizedCollectionName description={q(t['pluralName'])} languagecode="{LCID}" />
          </LocalizedCollectionNames>
          <Descriptions>
            <Description description={q(t['description'])} languagecode="{LCID}" />
          </Descriptions>
          <attributes>
{attrs}          </attributes>
          <EntitySetName>{ln}s</EntitySetName>
          <IsDuplicateCheckSupported>0</IsDuplicateCheckSupported>
          <IsBusinessProcessEnabled>{1 if ln == 'cin_inspection' else 0}</IsBusinessProcessEnabled>
          <IsRequiredOffline>0</IsRequiredOffline>
          <IsInteractionCentricEnabled>0</IsInteractionCentricEnabled>
          <IsCollaboration>0</IsCollaboration>
          <AutoRouteToOwnerQueue>0</AutoRouteToOwnerQueue>
          <IsConnectionsEnabled>0</IsConnectionsEnabled>
          <EntityColor></EntityColor>
          <IsDocumentManagementEnabled>0</IsDocumentManagementEnabled>
          <IsOneNoteIntegrationEnabled>0</IsOneNoteIntegrationEnabled>
          <IsKnowledgeManagementEnabled>0</IsKnowledgeManagementEnabled>
          <IsSLAEnabled>0</IsSLAEnabled>
          <IsDocumentRecommendationsEnabled>0</IsDocumentRecommendationsEnabled>
          <IsBPFEntity>0</IsBPFEntity>
          <OwnershipTypeMask>{own}</OwnershipTypeMask>
          <TableType>Standard</TableType>
          <IsAuditEnabled>0</IsAuditEnabled>
          <IsRetrieveAuditEnabled>0</IsRetrieveAuditEnabled>
          <IsRetrieveMultipleAuditEnabled>0</IsRetrieveMultipleAuditEnabled>
          <IsActivity>0</IsActivity>
          <ActivityTypeMask></ActivityTypeMask>
          <IsActivityParty>0</IsActivityParty>
          <IsReplicated>0</IsReplicated>
          <IsReplicationUserFiltered>0</IsReplicationUserFiltered>
          <IsMailMergeEnabled>0</IsMailMergeEnabled>
          <IsVisibleInMobile>0</IsVisibleInMobile>
          <IsVisibleInMobileClient>0</IsVisibleInMobileClient>
          <IsReadOnlyInMobileClient>0</IsReadOnlyInMobileClient>
          <IsOfflineInMobileClient>0</IsOfflineInMobileClient>
          <DaysSinceRecordLastModifiedMaxValue></DaysSinceRecordLastModifiedMaxValue>
          <EnforceStateTransitions>0</EnforceStateTransitions>
          <IsQuickCreateEnabled>{qc}</IsQuickCreateEnabled>
          <EntityHelpUrlEnabled>0</EntityHelpUrlEnabled>
          <EntityHelpUrl></EntityHelpUrl>
          <ChangeTrackingEnabled>0</ChangeTrackingEnabled>
          <IsEnabledForExternalChannels>0</IsEnabledForExternalChannels>
          <IntroducedVersion>{VERSION}</IntroducedVersion>
          <IsCustomizable>1</IsCustomizable>
          <IsRenameable>1</IsRenameable>
          <IsMappable>1</IsMappable>
          <CanModifyAuditSettings>1</CanModifyAuditSettings>
          <CanModifyMobileVisibility>1</CanModifyMobileVisibility>
          <CanModifyMobileClientVisibility>1</CanModifyMobileClientVisibility>
          <CanModifyMobileClientReadOnly>1</CanModifyMobileClientReadOnly>
          <CanModifyMobileClientOffline>1</CanModifyMobileClientOffline>
          <CanModifyConnectionSettings>1</CanModifyConnectionSettings>
          <CanModifyDuplicateDetectionSettings>1</CanModifyDuplicateDetectionSettings>
          <CanModifyMailMergeSettings>1</CanModifyMailMergeSettings>
          <CanModifyQueueSettings>1</CanModifyQueueSettings>
          <CanCreateAttributes>1</CanCreateAttributes>
          <CanCreateForms>1</CanCreateForms>
          <CanCreateCharts>1</CanCreateCharts>
          <CanCreateViews>1</CanCreateViews>
          <CanModifyAdditionalSettings>1</CanModifyAdditionalSettings>
          <CanChangeHierarchicalRelationship>1</CanChangeHierarchicalRelationship>
          <CanChangeTrackingBeEnabled>1</CanChangeTrackingBeEnabled>
          <CanEnableSyncToExternalSearchIndex>1</CanEnableSyncToExternalSearchIndex>
        </entity>
      </EntityInfo>
{{FORMS}}{{VIEWS}}{{CHARTS}}      <RibbonDiffXml>
        <CustomActions />
        <Templates>
          <RibbonTemplates Id="Mscrm.Templates"></RibbonTemplates>
        </Templates>
        <CommandDefinitions />
        <RuleDefinitions>
          <TabDisplayRules />
          <DisplayRules />
          <EnableRules />
        </RuleDefinitions>
        <LocLabels />
      </RibbonDiffXml>
    </Entity>
"""


# ---------------------------------------------------------------- forms
def cell(m, table, form_key, col_name, idx):
    col = m.column(table, col_name)
    t = col["type"]
    cid = gid("cell", table, form_key, col_name)
    cls = CLASS.get(t, CLASS["string"])
    disabled = "true" if (col_name == m.tables[table]["primaryName"]["logicalName"] and m.tables[table]["primaryName"].get("autoNumber")) else "false"
    return (f'                    <cell id="{cid}" showlabel="true" locklevel="0">\n'
            f'                      <labels>{label(col["displayName"] if t != "system" else col_name)}</labels>\n'
            f'                      <control id="{("header_" + col_name) if form_key == "header" else col_name}" classid="{cls}" datafieldname="{col_name}" disabled="{disabled}" />\n'
            f'                    </cell>\n')


def subgrid_cell(m, table, form_key, sg):
    cid = gid("cell", table, form_key, sg["name"])
    view = m.view_id(sg["target"], sg["view"])
    return (f'                    <cell id="{cid}" showlabel="false" rowspan="6" colspan="1">\n'
            f'                      <labels>{label(sg["name"])}</labels>\n'
            f'                      <control id="{sg["name"]}" classid="{CLASS["subgrid"]}">\n'
            f'                        <parameters>\n'
            f'                          <ViewId>{view}</ViewId>\n'
            f'                          <IsUserView>false</IsUserView>\n'
            f'                          <RelationshipName>{sg["relationship"]}</RelationshipName>\n'
            f'                          <TargetEntityType>{sg["target"]}</TargetEntityType>\n'
            f'                          <AutoExpand>Fixed</AutoExpand>\n'
            f'                          <EnableQuickFind>false</EnableQuickFind>\n'
            f'                          <EnableViewPicker>false</EnableViewPicker>\n'
            f'                          <ViewIds>{view}</ViewIds>\n'
            f'                          <EnableJumpBar>false</EnableJumpBar>\n'
            f'                          <ChartGridMode>Grid</ChartGridMode>\n'
            f'                          <VisualizationId />\n'
            f'                          <IsUserChart>false</IsUserChart>\n'
            f'                          <EnableChartPicker>false</EnableChartPicker>\n'
            f'                          <RecordsPerPage>10</RecordsPerPage>\n'
            f'                        </parameters>\n'
            f'                      </control>\n'
            f'                    </cell>\n')


def main_form_xml(m, table, spec):
    tabs = []
    for tb in spec["tabs"]:
        sections = []
        for sec in tb["sections"]:
            if "subgrid" in sec:
                rows = f"                  <row>\n{subgrid_cell(m, table, 'main', sec['subgrid'])}                  </row>\n"
            else:
                rows = "".join(f"                  <row>\n{cell(m, table, 'main', f, i)}                  </row>\n" for i, f in enumerate(sec["fields"]))
            sections.append(
                f'              <section showlabel="true" showbar="false" IsUserDefined="0" id="{gid("section", table, tb["name"], sec["name"])}" '
                f'name="{sec["name"]}" columns="11">\n                <labels>{label(sec["label"])}</labels>\n                <rows>\n{rows}                </rows>\n              </section>\n')
        tabs.append(
            f'        <tab verticallayout="true" id="{gid("tab", table, tb["name"])}" IsUserDefined="0" name="{tb["name"]}" expanded="true" showlabel="true">\n'
            f'          <labels>{label(tb["label"])}</labels>\n          <columns>\n            <column width="100%">\n              <sections>\n'
            f'{"".join(sections)}              </sections>\n            </column>\n          </columns>\n        </tab>\n')
    header = ""
    if spec.get("header"):
        hrows = "".join(f"            <row>\n{cell(m, table, 'header', f, i)}            </row>\n" for i, f in enumerate(spec["header"]))
        header = (f'      <header id="{gid("header", table)}" celllabelposition="Top" columns="1111" labelwidth="115" celllabelalignment="Left">\n'
                  f'        <rows>\n{hrows}        </rows>\n      </header>\n')
    fid = m.form_id(table, "main")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<forms {XSI} type="main">
  <systemform>
    <formid>{fid}</formid>
    <IntroducedVersion>{VERSION}</IntroducedVersion>
    <FormPresentation>1</FormPresentation>
    <FormActivationState>1</FormActivationState>
    <form>
      <tabs>
{"".join(tabs)}      </tabs>
{header}      <DisplayConditions Order="0" FallbackForm="true">
        <Everyone />
      </DisplayConditions>
    </form>
    <IsCustomizable>1</IsCustomizable>
    <CanBeDeleted>1</CanBeDeleted>
    <LocalizedNames>
      <LocalizedName description={q(spec['name'])} languagecode="{LCID}" />
    </LocalizedNames>
    <Descriptions>
      <Description description="" languagecode="{LCID}" />
    </Descriptions>
  </systemform>
</forms>
"""


def quick_form_xml(m, table, spec):
    rows = "".join(f"                  <row>\n{cell(m, table, 'quick', f, i)}                  </row>\n" for i, f in enumerate(spec["fields"]))
    fid = m.form_id(table, "quick")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<forms {XSI} type="quick">
  <systemform>
    <formid>{fid}</formid>
    <IntroducedVersion>{VERSION}</IntroducedVersion>
    <FormPresentation>1</FormPresentation>
    <FormActivationState>1</FormActivationState>
    <form>
      <tabs>
        <tab verticallayout="true" id="{gid('tab', table, 'quick')}" IsUserDefined="0" name="quickcreate" expanded="true" showlabel="false">
          <labels>{label("Quick create")}</labels>
          <columns>
            <column width="100%">
              <sections>
                <section showlabel="false" showbar="false" IsUserDefined="0" id="{gid('section', table, 'quick')}" name="quickcreate_section" columns="1">
                  <labels>{label("Quick create")}</labels>
                  <rows>
{rows}                  </rows>
                </section>
              </sections>
            </column>
          </columns>
        </tab>
      </tabs>
      <DisplayConditions Order="0" FallbackForm="false">
        <Everyone />
      </DisplayConditions>
    </form>
    <IsCustomizable>1</IsCustomizable>
    <CanBeDeleted>1</CanBeDeleted>
    <LocalizedNames>
      <LocalizedName description={q(spec['name'])} languagecode="{LCID}" />
    </LocalizedNames>
    <Descriptions>
      <Description description="" languagecode="{LCID}" />
    </Descriptions>
  </systemform>
</forms>
"""


# ---------------------------------------------------------------- views
def condition(m, table, attr, op, value):
    col = m.column(table, attr)
    if op == "null":
        return f'<condition attribute="{attr}" operator="null" />'
    if col["type"] == "choice":
        value = m.option_value(col["choice"], int(value))
    return f'<condition attribute="{attr}" operator="{op}" value="{value}" />'


def view_xml(m, table, v):
    t = m.tables[table]
    pk = f"{table}id"
    cells = "".join(f'          <cell name="{c}" width="{w}" />\n' for c, w in v["columns"])
    attrs = "".join(f'        <attribute name="{c}" />\n' for c, _ in v["columns"])
    order = v.get("orderBy", t["primaryName"]["logicalName"])
    conds = ['<condition attribute="statecode" operator="eq" value="0" />'] + [condition(m, table, a, o, val) for a, o, val in v.get("filter", [])]
    jump = t["primaryName"]["logicalName"]
    return f"""<?xml version="1.0" encoding="utf-8"?>
<savedqueries {XSI}>
  <savedquery>
    <IsCustomizable>1</IsCustomizable>
    <CanBeDeleted>1</CanBeDeleted>
    <isquickfindquery>0</isquickfindquery>
    <isprivate>0</isprivate>
    <isdefault>{1 if v.get('default') else 0}</isdefault>
    <savedqueryid>{m.view_id(table, v['name'])}</savedqueryid>
    <layoutxml>
      <grid name="resultset" jump="{jump}" select="1" icon="1" preview="1">
        <row name="result" id="{pk}">
{cells}        </row>
      </grid>
    </layoutxml>
    <querytype>0</querytype>
    <fetchxml>
      <fetch version="1.0" mapping="logical">
        <entity name="{table}">
{attrs}          <attribute name="{pk}" />
          <order attribute="{order}" descending="{'true' if v.get('descending') else 'false'}" />
          <filter type="and">
            {"".join(conds)}
          </filter>
        </entity>
      </fetch>
    </fetchxml>
    <IntroducedVersion>{VERSION}</IntroducedVersion>
    <LocalizedNames>
      <LocalizedName description={q(v['name'])} languagecode="{LCID}" />
    </LocalizedNames>
  </savedquery>
</savedqueries>
"""


def quickfind_xml(m, table):
    t = m.tables[table]
    pk = f"{table}id"
    name = t["primaryName"]["logicalName"]
    searchable = [name] + [c["logicalName"] for c in t["columns"] if c["type"] in ("string", "email") and c["logicalName"] != name][:2]
    cond = "".join(f'<condition attribute="{c}" operator="like" value="{{0}}" />' for c in searchable)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<savedqueries {XSI}>
  <savedquery>
    <IsCustomizable>1</IsCustomizable>
    <CanBeDeleted>0</CanBeDeleted>
    <isquickfindquery>1</isquickfindquery>
    <isprivate>0</isprivate>
    <isdefault>1</isdefault>
    <savedqueryid>{m.view_id(table, 'Quick Find')}</savedqueryid>
    <layoutxml>
      <grid name="resultset" jump="{name}" select="1" icon="1" preview="1">
        <row name="result" id="{pk}">
          <cell name="{name}" width="200" />
        </row>
      </grid>
    </layoutxml>
    <querytype>4</querytype>
    <fetchxml>
      <fetch version="1.0" mapping="logical">
        <entity name="{table}">
          <attribute name="{name}" />
          <attribute name="{pk}" />
          <order attribute="{name}" descending="false" />
          <filter type="and">
            <condition attribute="statecode" operator="eq" value="0" />
          </filter>
          <filter type="or" isquickfindfields="1">
            {cond}
          </filter>
        </entity>
      </fetch>
    </fetchxml>
    <IntroducedVersion>{VERSION}</IntroducedVersion>
    <LocalizedNames>
      <LocalizedName description={q('Quick Find Active ' + t['pluralName'])} languagecode="{LCID}" />
    </LocalizedNames>
  </savedquery>
</savedqueries>
"""


# ---------------------------------------------------------------- charts and dashboard
def chart_xml(m, c):
    table, cat = c["table"], c["category"]
    pk = f"{table}id"
    flt = "".join(f"<filter type=\"and\">{condition(m, table, a, o, v)}</filter>" for a, o, v in c.get("filter", []))
    ctype = {"column": "Column", "bar": "Bar", "pie": "Pie"}[c["type"]]
    cid = m.chart_id(c["name"])
    return f"""<?xml version="1.0" encoding="utf-8"?>
<visualization {XSI}>
  <savedqueryvisualizationid>{cid}</savedqueryvisualizationid>
  <name>{escape(c['name'])}</name>
  <description></description>
  <primaryentitytypecode>{table}</primaryentitytypecode>
  <datadescription>
    <datadefinition>
      <fetchcollection>
        <fetch mapping="logical" aggregate="true">
          <entity name="{table}">
            <attribute name="{pk}" alias="count_{pk}" aggregate="count" />
            <attribute name="{cat}" groupby="true" alias="group_{cat}" />
            {flt}
          </entity>
        </fetch>
      </fetchcollection>
      <categorycollection>
        <category alias="group_{cat}">
          <measurecollection>
            <measure alias="count_{pk}" />
          </measurecollection>
        </category>
      </categorycollection>
    </datadefinition>
  </datadescription>
  <presentationdescription>
    <Chart Palette="None" PaletteCustomColors="55,118,193; 206,77,72; 134,171,70; 112,89,145; 70,170,197; 232,128,56">
      <Series>
        <Series ChartType="{ctype}" IsValueShownAsLabel="True" Font="{{0}}, 9.5px" LabelForeColor="59, 59, 59" CustomProperties="PointWidth=0.75, MaxPixelPointWidth=40">
          <SmartLabelStyle Enabled="True" />
        </Series>
      </Series>
      <ChartAreas>
        <ChartArea BorderColor="White" BorderDashStyle="Solid">
          <AxisY LabelAutoFitMinFontSize="8" TitleForeColor="59, 59, 59" TitleFont="{{0}}, 9.5px" LineColor="165, 172, 181" IntervalAutoMode="VariableCount">
            <MajorGrid LineColor="239, 242, 246" />
            <MajorTickMark LineColor="165, 172, 181" />
            <LabelStyle Font="{{0}}, 9.5px" ForeColor="59, 59, 59" />
          </AxisY>
          <AxisX LabelAutoFitMinFontSize="8" TitleForeColor="59, 59, 59" TitleFont="{{0}}, 9.5px" LineColor="165, 172, 181" IntervalAutoMode="VariableCount">
            <MajorTickMark LineColor="165, 172, 181" />
            <MajorGrid LineColor="Transparent" />
            <LabelStyle Font="{{0}}, 9.5px" ForeColor="59, 59, 59" />
          </AxisX>
        </ChartArea>
      </ChartAreas>
      <Titles>
        <Title Alignment="TopLeft" DockingOffset="-3" Font="{{0}}, 13px" ForeColor="59, 59, 59" />
      </Titles>
    </Chart>
  </presentationdescription>
  <isdefault>{1 if c['name'] == 'Inspections by status' else 0}</isdefault>
  <componentstate>0</componentstate>
  <introducedversion>{VERSION}</introducedversion>
</visualization>
"""


def dashboard_xml(m):
    d = m.s["ui"]["dashboard"]
    cells = []
    for i, comp in enumerate(d["components"]):
        chart = comp["kind"] == "chart"
        view = m.view_id(comp["table"], comp["view"])
        vis = m.chart_id(comp["chart"]) if chart else ""
        mode = "Chart" if chart else "Grid"
        cells.append(
            f'                <cell id="{gid("dashcell", str(i))}" showlabel="false" rowspan="8" colspan="1">\n'
            f'                  <labels>{label(comp.get("chart") or comp["view"])}</labels>\n'
            f'                  <control id="{"chart" if chart else "list"}_{i + 1}" classid="{CLASS["subgrid"]}">\n'
            f'                    <parameters>\n'
            f'                      <ViewId>{view}</ViewId>\n'
            f'                      <IsUserView>false</IsUserView>\n'
            f'                      <RelationshipName />\n'
            f'                      <TargetEntityType>{comp["table"]}</TargetEntityType>\n'
            f'                      <AutoExpand>Fixed</AutoExpand>\n'
            f'                      <EnableQuickFind>false</EnableQuickFind>\n'
            f'                      <EnableViewPicker>false</EnableViewPicker>\n'
            f'                      <ViewIds>{view}</ViewIds>\n'
            f'                      <EnableJumpBar>false</EnableJumpBar>\n'
            f'                      <ChartGridMode>{mode}</ChartGridMode>\n'
            f'                      <VisualizationId>{vis}</VisualizationId>\n'
            f'                      <IsUserChart>false</IsUserChart>\n'
            f'                      <EnableChartPicker>false</EnableChartPicker>\n'
            f'                      <RecordsPerPage>6</RecordsPerPage>\n'
            f'                    </parameters>\n'
            f'                  </control>\n'
            f'                </cell>\n')
    col = lambda cs: "".join(f"              <row>\n{c}              </row>\n" for c in cs)
    left, right = cells[0::2], cells[1::2]
    section = lambda cs, n: (f'            <section showlabel="false" showbar="false" IsUserDefined="0" id="{gid("dashsec", n)}" name="section_{n}" columns="1">\n'
                              f'              <labels>{label("Section")}</labels>\n              <rows>\n{col(cs)}              </rows>\n            </section>\n')
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Dashboard {XSI}>
  <FormId>{m.dashboard_id}</FormId>
  <IntroducedVersion>{VERSION}</IntroducedVersion>
  <FormPresentation>1</FormPresentation>
  <FormActivationState>1</FormActivationState>
  <form>
    <tabs>
      <tab verticallayout="true" id="{gid('dashtab')}" IsUserDefined="0" name="dashboard" expanded="true" showlabel="false">
        <labels>{label("Dashboard")}</labels>
        <columns>
          <column width="50%">
            <sections>
{section(left, 'left')}            </sections>
          </column>
          <column width="50%">
            <sections>
{section(right, 'right')}            </sections>
          </column>
        </columns>
      </tab>
    </tabs>
  </form>
  <IsCustomizable>1</IsCustomizable>
  <CanBeDeleted>1</CanBeDeleted>
  <LocalizedNames>
    <LocalizedName description={q(d['name'])} languagecode="{LCID}" />
  </LocalizedNames>
  <Descriptions>
    <Description description="" languagecode="{LCID}" />
  </Descriptions>
</Dashboard>
"""


# ---------------------------------------------------------------- app, sitemap
def sitemap_xml(m):
    app = m.s["ui"]["app"]
    areas = []
    for ai, area in enumerate(app["sitemap"]):
        groups = []
        for gi, g in enumerate(area["groups"]):
            subs = []
            for p in g["pages"]:
                if p["type"] == "table":
                    sid = f"SubArea_{p['table']}"
                    subs.append(f'            <SubArea Id="{sid}" Entity="{p["table"]}" Client="All" PassParams="false" AvailableOffline="true" '
                                f'IntroducedVersion="{VERSION}"><Titles><Title LCID="{LCID}" Title={q(p["title"])} /></Titles></SubArea>\n')
                else:
                    did = m.dashboard_id.strip("{}").lower()
                    subs.append(f'            <SubArea Id="SubArea_Dashboard" Url="/main.aspx?pagetype=dashboard&amp;id=%7b{did}%7d" Client="All" '
                                f'PassParams="false" AvailableOffline="true" IntroducedVersion="{VERSION}"><Titles><Title LCID="{LCID}" Title={q(p["title"])} /></Titles></SubArea>\n')
            groups.append(f'          <Group Id="Group_{g["group"].replace(" ", "")}" IsProfile="false" IntroducedVersion="{VERSION}">\n'
                          f'            <Titles><Title LCID="{LCID}" Title={q(g["group"])} /></Titles>\n{"".join(subs)}          </Group>\n')
        areas.append(f'        <Area Id="Area_{area["area"].replace(" ", "")}" ShowGroups="true" IntroducedVersion="{VERSION}">\n'
                     f'          <Titles><Title LCID="{LCID}" Title={q(area["area"])} /></Titles>\n{"".join(groups)}        </Area>\n')
    return f'<SiteMap IntroducedVersion="{VERSION}">\n{"".join(areas)}      </SiteMap>'


def appmodule_xml(m):
    app = m.s["ui"]["app"]
    comps = []
    tables = [p["table"] for a in app["sitemap"] for g in a["groups"] for p in g["pages"] if p["type"] == "table"]
    for tb in tables:
        comps.append(f'          <AppModuleComponent type="1" schemaName="{tb}" />')
    comps.append(f'          <AppModuleComponent type="62" id="{m.sitemap_id}" />')
    comps.append(f'          <AppModuleComponent type="60" id="{m.dashboard_id}" />')
    for tb in tables:
        for v in m.s["ui"]["views"].get(tb, []):
            comps.append(f'          <AppModuleComponent type="26" id="{m.view_id(tb, v["name"])}" />')
        comps.append(f'          <AppModuleComponent type="60" id="{m.form_id(tb, "main")}" />')
        if m.s["ui"]["forms"].get(tb, {}).get("quickCreate"):
            comps.append(f'          <AppModuleComponent type="60" id="{m.form_id(tb, "quick")}" />')
    for c in m.s["ui"]["charts"]:
        comps.append(f'          <AppModuleComponent type="59" id="{m.chart_id(c["name"])}" />')
    roles = "".join(f'          <Role id="{m.role_id(r)}" />\n' for r in app["roles"])
    return f"""    <AppModule>
      <UniqueName>{app['uniqueName']}</UniqueName>
      <IntroducedVersion>{VERSION}</IntroducedVersion>
      <IsDefault>0</IsDefault>
      <IsFeatured>0</IsFeatured>
      <ConfigurationId xsi:nil="true"></ConfigurationId>
      <ClientType>4</ClientType>
      <FormFactor>1</FormFactor>
      <NavigationType>0</NavigationType>
      <statecode>0</statecode>
      <statuscode>1</statuscode>
      <AppModuleComponents>
{chr(10).join(comps)}
      </AppModuleComponents>
      <AppModuleRoleMaps>
{roles}      </AppModuleRoleMaps>
      <LocalizedNames>
        <LocalizedName description={q(app['name'])} languagecode="{LCID}" />
      </LocalizedNames>
      <Descriptions>
        <Description description={q(app['description'])} languagecode="{LCID}" />
      </Descriptions>
    </AppModule>
"""


# ---------------------------------------------------------------- security
def role_xml(m, r):
    privs = []
    for table, ops in r["privileges"].items():
        for op, level in ops.items():
            privs.append(f'        <RolePrivilege name="prv{op}{table}" level="{PRIV_LEVEL[level]}" />')
    return f"""    <Role id="{m.role_id(r['name'])}">
      <Name>{escape(r['name'])}</Name>
      <IsCustomizable>1</IsCustomizable>
      <CanBeDeleted>1</CanBeDeleted>
      <RolePrivileges>
{chr(10).join(privs)}
      </RolePrivileges>
    </Role>
"""


def fsp_xml(m, p):
    perms = "".join(
        f'        <FieldPermission entityname="{x["table"]}" attributelogicalname="{x["column"]}" '
        f'cancreate="{4 if x["create"] else 0}" canread="{4 if x["read"] else 0}" canupdate="{4 if x["update"] else 0}" />\n'
        for x in p["permissions"])
    return f"""    <FieldSecurityProfile fieldsecurityprofileid="{m.profile_id(p['name'])}" name={q(p['name'])}>
      <description>{escape(p['description'])}</description>
      <FieldPermissions>
{perms}      </FieldPermissions>
    </FieldSecurityProfile>
"""


# ---------------------------------------------------------------- relationships
def relationship_xml(m, r):
    ref, ing = r["referenced"], r["referencing"]
    delete, assign = BEHAVIOR[r["delete"]]
    parental = r.get("parental")
    return f"""    <EntityRelationship Name="{r['name']}">
      <EntityRelationshipType>OneToMany</EntityRelationshipType>
      <IsCustomizable>1</IsCustomizable>
      <IntroducedVersion>{VERSION}</IntroducedVersion>
      <IsHierarchical>0</IsHierarchical>
      <ReferencingEntityName>{ing}</ReferencingEntityName>
      <ReferencedEntityName>{ref}</ReferencedEntityName>
      <CascadeAssign>{'Cascade' if parental else 'NoCascade'}</CascadeAssign>
      <CascadeDelete>{delete}</CascadeDelete>
      <CascadeReparent>{'Cascade' if parental else 'NoCascade'}</CascadeReparent>
      <CascadeShare>{'Cascade' if parental else 'NoCascade'}</CascadeShare>
      <CascadeUnshare>{'Cascade' if parental else 'NoCascade'}</CascadeUnshare>
      <CascadeRollupView>NoCascade</CascadeRollupView>
      <IsValidForAdvancedFind>1</IsValidForAdvancedFind>
      <ReferencingAttributeName>{r['lookup']}</ReferencingAttributeName>
      <RelationshipDescription>
        <Descriptions>
          <Description description="" languagecode="{LCID}" />
        </Descriptions>
      </RelationshipDescription>
      <EntityRelationshipRoles>
        <EntityRelationshipRole>
          <NavPaneDisplayOption>UseCollectionName</NavPaneDisplayOption>
          <NavPaneArea>Details</NavPaneArea>
          <NavPaneOrder>10000</NavPaneOrder>
          <NavigationPropertyName>{r['lookup']}</NavigationPropertyName>
          <RelationshipRoleType>1</RelationshipRoleType>
        </EntityRelationshipRole>
        <EntityRelationshipRole>
          <NavPaneDisplayOption>NoDisplay</NavPaneDisplayOption>
          <NavPaneArea>Details</NavPaneArea>
          <NavPaneOrder>10000</NavPaneOrder>
          <NavigationPropertyName>{r['name']}</NavigationPropertyName>
          <RelationshipRoleType>0</RelationshipRoleType>
        </EntityRelationshipRole>
      </EntityRelationshipRoles>
    </EntityRelationship>
"""


# ---------------------------------------------------------------- assembling
def solution_xml(m, profile):
    s, p = m.s["solution"], m.s["publisher"]
    roots = [f'      <RootComponent type="1" schemaName="{t}" behavior="0" />' for t in m.tables]
    if profile == "full":
        app = m.s["ui"]["app"]
        roots += [f'      <RootComponent type="60" id="{m.dashboard_id}" behavior="0" />',
                  # SolutionPackager (pac 2.16.1) only accepts the app and its site map by unique name here:
                  # with id="{guid}" it stops with "RootComponent validation failed".
                  f'      <RootComponent type="62" schemaName="{app["uniqueName"]}" behavior="0" />',
                  f'      <RootComponent type="80" schemaName="{app["uniqueName"]}" behavior="0" />']
        roots += [f'      <RootComponent type="20" id="{m.role_id(r["name"])}" behavior="0" />' for r in m.s["security"]["roles"]]
        roots += [f'      <RootComponent type="70" id="{m.profile_id(f["name"])}" behavior="0" />' for f in m.s["security"]["fieldSecurityProfiles"]]
    addr = "".join(f"""        <Address>
          <AddressNumber>{i}</AddressNumber>
          <AddressTypeCode>1</AddressTypeCode>
          <ShippingMethodCode>1</ShippingMethodCode>
        </Address>
""" for i in (1, 2))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml version="9.2.0.0" SolutionPackageVersion="9.2" languagecode="{LCID}" generatedBy="CrmLive" {XSI}>
  <SolutionManifest>
    <UniqueName>{s['uniqueName']}</UniqueName>
    <LocalizedNames>
      <LocalizedName description={q(s['displayName'])} languagecode="{LCID}" />
    </LocalizedNames>
    <Descriptions>
      <Description description={q(s['description'])} languagecode="{LCID}" />
    </Descriptions>
    <Version>{m.s['version']}</Version>
    <Managed>0</Managed>
    <Publisher>
      <UniqueName>{p['uniqueName']}</UniqueName>
      <LocalizedNames>
        <LocalizedName description={q(p['displayName'])} languagecode="{LCID}" />
      </LocalizedNames>
      <Descriptions>
        <Description description={q(p['description'])} languagecode="{LCID}" />
      </Descriptions>
      <EMailAddress xsi:nil="true"></EMailAddress>
      <SupportingWebsiteUrl xsi:nil="true"></SupportingWebsiteUrl>
      <CustomizationPrefix>{p['prefix']}</CustomizationPrefix>
      <CustomizationOptionValuePrefix>{p['optionValuePrefix']}</CustomizationOptionValuePrefix>
      <Addresses>
{addr}      </Addresses>
    </Publisher>
    <RootComponents>
{chr(10).join(roots)}
    </RootComponents>
    <MissingDependencies />
  </SolutionManifest>
</ImportExportXml>
"""


def inner(xml, tag):
    """The <tag>...</tag> element of a generated file, without the XML declaration or the wrapper element."""
    a = xml.index(f"<{tag}>")
    b = xml.index(f"</{tag}>") + len(tag) + 3
    return xml[a:b] + "\n"


def customizations_xml(m, profile):
    ui = m.s["ui"]
    ents = []
    for ln, t in m.tables.items():
        x = entity_xml(m, t)
        forms = views = charts = ""
        if profile == "full":
            f = ui["forms"].get(ln, {})
            fx = ""
            if "main" in f:
                fx += main_form_xml(m, ln, f["main"]).split("\n", 1)[1]
            if "quickCreate" in f:
                fx += quick_form_xml(m, ln, f["quickCreate"]).split("\n", 1)[1]
            forms = f"      <FormXml>\n{fx}      </FormXml>\n"
            vx = inner(quickfind_xml(m, ln), "savedquery")
            vx += "".join(inner(view_xml(m, ln, v), "savedquery") for v in ui["views"].get(ln, []))
            views = f"      <SavedQueries>\n      <savedqueries>\n{vx}      </savedqueries>\n      </SavedQueries>\n"
            cx = "".join(chart_xml(m, c).split("\n", 1)[1] for c in ui["charts"] if c["table"] == ln)
            charts = f"      <Visualizations>\n{cx}      </Visualizations>\n" if cx else ""
        ents.append(x.replace("{FORMS}", forms).replace("{VIEWS}", views).replace("{CHARTS}", charts))
    rels = "".join(relationship_xml(m, r) for r in m.s["relationships"])
    roles = fsps = dashboards = appmods = sitemaps = ""
    if profile == "full":
        roles = "".join(role_xml(m, r) for r in m.s["security"]["roles"])
        fsps = "".join(fsp_xml(m, p) for p in m.s["security"]["fieldSecurityProfiles"])
        dashboards = f"  <Dashboards>\n{dashboard_xml(m).split(chr(10), 1)[1]}  </Dashboards>\n"
        app = ui["app"]
        sitemaps = (f"  <AppModuleSiteMaps>\n    <AppModuleSiteMap>\n      <SiteMapUniqueName>{app['uniqueName']}</SiteMapUniqueName>\n"
                    f"      <SiteMapId>{m.sitemap_id}</SiteMapId>\n      {sitemap_xml(m)}\n    </AppModuleSiteMap>\n  </AppModuleSiteMaps>\n")
        appmods = f"  <AppModules>\n{appmodule_xml(m)}  </AppModules>\n"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml {XSI}>
  <Entities>
{"".join(ents)}  </Entities>
  <Roles>
{roles}  </Roles>
  <Workflows />
  <FieldSecurityProfiles>
{fsps}  </FieldSecurityProfiles>
{dashboards}  <Templates />
  <EntityMaps />
  <EntityRelationships>
{rels}  </EntityRelationships>
  <OrganizationSettings />
  <optionsets />
  <CustomControls />
{sitemaps}{appmods}  <SolutionPluginAssemblies />
  <EntityDataProviders />
  <Languages>
    <Language>{LCID}</Language>
  </Languages>
</ImportExportXml>
"""


def content_types():
    return ('<?xml version="1.0" encoding="utf-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/octet-stream" /></Types>')


def build_export_files(schema, profile):
    m = Model(schema)
    return {
        "solution.xml": solution_xml(m, profile),
        "customizations.xml": customizations_xml(m, profile),
        "[Content_Types].xml": content_types(),
    }


def write_zip(files, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text.encode("utf-8"))
    return path


def unpack(pac, zip_path, out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    cmd = [pac, "solution", "unpack", "--zipfile", str(zip_path), "--folder", str(out), "--packagetype", "Unmanaged", "--allowDelete", "true"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"pac solution unpack failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schema", default=str(SCHEMA))
    ap.add_argument("--profile", choices=["data", "full"], default="full")
    ap.add_argument("--out", help="folder for the unpacked solution source")
    ap.add_argument("--export-zip", help="write the export-format zip here and stop")
    ap.add_argument("--pac", default="pac")
    a = ap.parse_args(argv)
    schema = load(a.schema)
    files = build_export_files(schema, a.profile)
    if a.export_zip:
        print(write_zip(files, a.export_zip))
        return
    if not a.out:
        ap.error("--out or --export-zip is required")
    with tempfile.TemporaryDirectory() as tmp:
        z = write_zip(files, Path(tmp) / "export.zip")
        print(unpack(a.pac, z, a.out))


if __name__ == "__main__":
    main()
