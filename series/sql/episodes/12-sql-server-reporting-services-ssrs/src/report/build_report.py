"""Writes SalesByProduct.rdl, the paginated report of episode 12 (RDL schema 2016/01, SQL Server 2022 Reporting Services).

    python src/report/build_report.py            # rewrites src/report/SalesByProduct.rdl
    python src/report/build_report.py --check    # exit 1 when the file on disk differs from what this writes

One table (FIELDS) drives the dataset's fields and the table's columns, and the parameter definitions drive the
dataset's query parameters, so a rename cannot leave the report pointing at a field that no longer exists.
The result is validated against Microsoft's RDL 2016/01 XSD by tests/test_rdl.py (when the schema can be fetched)
and cross-checked against the stored procedures by tests/test_local.py. Whether Report Builder and the report
server open and render it is checked in the recording (demo.md).
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).with_name("SalesByProduct.rdl")
NS = uuid.UUID("6f1c2f0e-0000-4000-8000-000000000012")
DATA_SOURCE = "ContosoBikesRpt"
DATA_SOURCE_PATH = "/MGLab/ContosoBikesRpt"           # shared data source on the report server (deploy script creates it)

# name, RDL type, header text, width (cm), format, aligned right
FIELDS = [
    ("ProductName", "System.String", "Product", 7.0, None, False),
    ("UnitsSold", "System.Int32", "Units sold", 3.0, "#,##0", True),
    ("Orders", "System.Int32", "Orders", 3.0, "#,##0", True),
    ("Revenue", "System.Decimal", "Revenue", 4.0, "#,##0.00", True),
]
# name, RDL type, prompt, default (expression-free literal), data type for the stored procedure parameter
PARAMS = [
    ("From", "DateTime", "From", "2025-03-01T00:00:00"),
    ("To", "DateTime", "To", "2025-04-30T00:00:00"),
    ("Region", "String", "Region", "ALL"),
]
PROC_SALES, PROC_REGIONS = "Rpt.usp_SalesByProduct", "Rpt.usp_Regions"
REGION_FIELDS = [("RegionCode", "System.String"), ("RegionName", "System.String")]
SUBTITLE = ('="From " & Format(Parameters!From.Value, "yyyy-MM-dd") & " to " & Format(Parameters!To.Value, "yyyy-MM-dd")'
            ' & "  |  " & Parameters!Region.Label')
FOOTER_TEXT = '="Run " & Format(Globals!ExecutionTime, "yyyy-MM-dd HH:mm") & "  |  Page " & Globals!PageNumber & " of " & Globals!TotalPages'


def gid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def cell(name: str, value: str, bold=False, right=False, fmt=None, border=True, shade=False, expr=False) -> str:
    style = ""
    if bold:
        style += "<FontWeight>Bold</FontWeight>"
    if fmt:
        style += f"<Format>{escape(fmt)}</Format>"
    align = "<TextAlign>Right</TextAlign>" if right else ""
    border_xml = "<Border><Style>None</Style></Border><BottomBorder><Color>LightGrey</Color><Style>Solid</Style></BottomBorder>" if border else ""
    fill = "<BackgroundColor>#e8eef7</BackgroundColor>" if shade else ""
    return f'''            <TablixCell>
              <CellContents>
                <Textbox Name="{name}">
                  <CanGrow>true</CanGrow>
                  <KeepTogether>true</KeepTogether>
                  <Paragraphs>
                    <Paragraph>
                      <TextRuns>
                        <TextRun>
                          <Value>{escape(value)}</Value>
                          <Style>{style}</Style>
                        </TextRun>
                      </TextRuns>
                      <Style>{align}</Style>
                    </Paragraph>
                  </Paragraphs>
                  <rd:DefaultName>{name}</rd:DefaultName>
                  <Style>{border_xml}{fill}<PaddingLeft>2pt</PaddingLeft><PaddingRight>2pt</PaddingRight><PaddingTop>2pt</PaddingTop><PaddingBottom>2pt</PaddingBottom></Style>
                </Textbox>
              </CellContents>
            </TablixCell>'''


def textbox(name: str, value: str, top: float, height: float, width: float, size: str, bold=False) -> str:
    return f'''        <Textbox Name="{name}">
          <CanGrow>true</CanGrow>
          <KeepTogether>true</KeepTogether>
          <Paragraphs>
            <Paragraph>
              <TextRuns>
                <TextRun>
                  <Value>{escape(value)}</Value>
                  <Style><FontSize>{size}</FontSize>{"<FontWeight>Bold</FontWeight>" if bold else ""}</Style>
                </TextRun>
              </TextRuns>
              <Style />
            </Paragraph>
          </Paragraphs>
          <rd:DefaultName>{name}</rd:DefaultName>
          <Top>{top}cm</Top>
          <Left>0cm</Left>
          <Height>{height}cm</Height>
          <Width>{width}cm</Width>
          <Style><PaddingLeft>2pt</PaddingLeft><PaddingRight>2pt</PaddingRight><PaddingTop>2pt</PaddingTop><PaddingBottom>2pt</PaddingBottom></Style>
        </Textbox>'''


def tablix() -> str:
    width = sum(f[3] for f in FIELDS)
    cols = "\n".join(f"        <TablixColumn><Width>{f[3]}cm</Width></TablixColumn>" for f in FIELDS)
    head = "\n".join(cell(f"h{f[0]}", f[2], bold=True, right=f[5], shade=True) for f in FIELDS)
    det = "\n".join(cell(f[0], f"=Fields!{f[0]}.Value", right=f[5], fmt=f[4]) for f in FIELDS)
    foot_vals = {"ProductName": "Total", "UnitsSold": "=Sum(Fields!UnitsSold.Value)", "Orders": "", "Revenue": "=Sum(Fields!Revenue.Value)"}
    foot = "\n".join(cell(f"t{f[0]}", foot_vals[f[0]], bold=True, right=f[5], fmt=f[4], shade=True) for f in FIELDS)
    members = "\n".join("        <TablixMember />" for _ in FIELDS)
    return f'''        <Tablix Name="SalesTable">
          <TablixBody>
            <TablixColumns>
{cols}
            </TablixColumns>
            <TablixRows>
              <TablixRow>
                <Height>0.7cm</Height>
                <TablixCells>
{head}
                </TablixCells>
              </TablixRow>
              <TablixRow>
                <Height>0.6cm</Height>
                <TablixCells>
{det}
                </TablixCells>
              </TablixRow>
              <TablixRow>
                <Height>0.7cm</Height>
                <TablixCells>
{foot}
                </TablixCells>
              </TablixRow>
            </TablixRows>
          </TablixBody>
          <TablixColumnHierarchy>
            <TablixMembers>
{members}
            </TablixMembers>
          </TablixColumnHierarchy>
          <TablixRowHierarchy>
            <TablixMembers>
              <TablixMember>
                <KeepWithGroup>After</KeepWithGroup>
                <RepeatOnNewPage>true</RepeatOnNewPage>
              </TablixMember>
              <TablixMember>
                <Group Name="Details" />
              </TablixMember>
              <TablixMember>
                <KeepWithGroup>Before</KeepWithGroup>
              </TablixMember>
            </TablixMembers>
          </TablixRowHierarchy>
          <DataSetName>SalesByProduct</DataSetName>
          <Top>2.2cm</Top>
          <Left>0cm</Left>
          <Height>2.0cm</Height>
          <Width>{width}cm</Width>
          <Style><Border><Style>None</Style></Border></Style>
        </Tablix>'''


def fields_xml(fields) -> str:
    return "\n".join(f'''        <Field Name="{n}">
          <DataField>{n}</DataField>
          <rd:TypeName>{t}</rd:TypeName>
        </Field>''' for n, t in fields)


def build() -> str:
    width = sum(f[3] for f in FIELDS)
    qparams = "\n".join(f'''          <QueryParameter Name="@{n}">
            <Value>=Parameters!{n}.Value</Value>
          </QueryParameter>''' for n, *_ in PARAMS)
    rparams = []
    for n, t, prompt, default in PARAMS:
        valid = ""
        if n == "Region":
            valid = '''
      <ValidValues>
        <DataSetReference>
          <DataSetName>Regions</DataSetName>
          <ValueField>RegionCode</ValueField>
          <LabelField>RegionName</LabelField>
        </DataSetReference>
      </ValidValues>'''
        rparams.append(f'''    <ReportParameter Name="{n}">
      <DataType>{t}</DataType>
      <DefaultValue>
        <Values>
          <Value>{default}</Value>
        </Values>
      </DefaultValue>
      <Prompt>{prompt}</Prompt>{valid}
    </ReportParameter>''')
    layout_cells = "\n".join(f'''        <CellDefinition>
          <ColumnIndex>{i}</ColumnIndex>
          <RowIndex>0</RowIndex>
          <ParameterName>{n}</ParameterName>
        </CellDefinition>''' for i, (n, *_) in enumerate(PARAMS))
    return f'''<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition" xmlns:rd="http://schemas.microsoft.com/SQLServer/reporting/reportdesigner">
  <Description>Contoso Bikes: units, orders and revenue per product for a date range and a region.</Description>
  <AutoRefresh>0</AutoRefresh>
  <DataSources>
    <DataSource Name="{DATA_SOURCE}">
      <DataSourceReference>{DATA_SOURCE_PATH}</DataSourceReference>
      <rd:SecurityType>None</rd:SecurityType>
      <rd:DataSourceID>{gid("datasource")}</rd:DataSourceID>
    </DataSource>
  </DataSources>
  <DataSets>
    <DataSet Name="SalesByProduct">
      <Query>
        <DataSourceName>{DATA_SOURCE}</DataSourceName>
        <QueryParameters>
{qparams}
        </QueryParameters>
        <CommandType>StoredProcedure</CommandType>
        <CommandText>{PROC_SALES}</CommandText>
      </Query>
      <Fields>
{fields_xml([(f[0], f[1]) for f in FIELDS])}
      </Fields>
    </DataSet>
    <DataSet Name="Regions">
      <Query>
        <DataSourceName>{DATA_SOURCE}</DataSourceName>
        <CommandType>StoredProcedure</CommandType>
        <CommandText>{PROC_REGIONS}</CommandText>
      </Query>
      <Fields>
{fields_xml(REGION_FIELDS)}
      </Fields>
    </DataSet>
  </DataSets>
  <ReportSections>
    <ReportSection>
      <Body>
        <ReportItems>
{textbox("Title", "Contoso Bikes: sales by product", 0, 1.0, width, "16pt", bold=True)}
{textbox("Subtitle", SUBTITLE, 1.0, 0.8, width, "10pt")}
{tablix()}
        </ReportItems>
        <Height>4.4cm</Height>
        <Style />
      </Body>
      <Width>{width}cm</Width>
      <Page>
        <PageFooter>
          <Height>0.8cm</Height>
          <PrintOnFirstPage>true</PrintOnFirstPage>
          <PrintOnLastPage>true</PrintOnLastPage>
          <ReportItems>
{textbox("FooterText", FOOTER_TEXT, 0.1, 0.6, width, "8pt")}
          </ReportItems>
          <Style />
        </PageFooter>
        <PageHeight>21cm</PageHeight>
        <PageWidth>29.7cm</PageWidth>
        <LeftMargin>1.5cm</LeftMargin>
        <RightMargin>1.5cm</RightMargin>
        <TopMargin>1.5cm</TopMargin>
        <BottomMargin>1.5cm</BottomMargin>
        <Style />
      </Page>
    </ReportSection>
  </ReportSections>
  <ReportParameters>
{chr(10).join(rparams)}
  </ReportParameters>
  <ReportParametersLayout>
    <GridLayoutDefinition>
      <NumberOfColumns>3</NumberOfColumns>
      <NumberOfRows>1</NumberOfRows>
      <CellDefinitions>
{layout_cells}
      </CellDefinitions>
    </GridLayoutDefinition>
  </ReportParametersLayout>
  <Language>en-US</Language>
  <rd:ReportUnitType>Cm</rd:ReportUnitType>
  <rd:ReportID>{gid("report")}</rd:ReportID>
</Report>
'''


if __name__ == "__main__":
    text = build()
    if "--check" in sys.argv:
        sys.exit(0 if OUT.exists() and OUT.read_text(encoding="utf-8") == text else 1)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({len(text)} bytes)")
