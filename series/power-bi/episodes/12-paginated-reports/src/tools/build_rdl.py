#!/usr/bin/env python3
"""Writes the paginated report ContosoStoreStatement.rdl (RDL 2016/01) from this script, so every size and name has one source.

  python3 build_rdl.py                 # writes ../report/ContosoStoreStatement.rdl
  python3 build_rdl.py --check         # fails when the committed file is out of date

The report: A4 portrait, one page per store (page break between groups), the column header rows repeat on every page of a store,
page header with the title and year, page footer with "Page n of m". Data: the DAX in ../dax/store-statement.dax against the
published semantic model (Analysis Services data source, powerbi:// connection string: no dataset id inside the file).
Not a Power BI Report Builder file: nobody has opened it in Report Builder yet (see the README, "Not verified").
"""
import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "report" / "ContosoStoreStatement.rdl"
DAX = HERE.parent / "dax" / "store-statement.dax"

WORKSPACE = "Contoso Sales (Lab)"
MODEL = "ContosoSales"
PAGE_W, PAGE_H = 8.27, 11.69            # inches, A4 portrait
MARGIN = 0.75
COLS = [("Month", 1.7), ("Sales Amount", 1.9), ("Units", 1.4), ("Margin %", 1.5)]     # body width 6.5 = page 8.27 - 2 x 0.75 - 0.27 spare
BODY_W = round(sum(w for _, w in COLS), 2)
FONT = "Segoe UI"
NS = "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"
RD = "http://schemas.microsoft.com/SQLServer/reporting/reportdesigner"

# (report field name, DAX result column, value expression, format, alignment)
FIELDS = [
    ("Store", "Store[Store]", None, None),
    ("MonthNumber", "Date[Month Number]", None, None),
    ("Month", "Date[Month]", None, None),
    ("SalesAmount", "[Sales Amount]", None, None),
    ("Units", "[Units]", None, None),
    ("MarginPct", "[Margin %]", None, None),
]
CELLS = [("Month", "=Fields!Month.Value", None, "Left"),
         ("Sales Amount", "=Fields!SalesAmount.Value", "#,##0.00", "Right"),
         ("Units", "=Fields!Units.Value", "#,##0", "Right"),
         ("Margin %", "=Fields!MarginPct.Value", "0.0%", "Right")]


def style(size="10pt", weight="Default", color="Black", align=None, fill=None, border=None, pad=True):
    s = f"<Style>"
    if border:
        s += f"<Border><Style>None</Style></Border><BottomBorder><Color>{border}</Color><Style>Solid</Style><Width>0.75pt</Width></BottomBorder>"
    if fill:
        s += f"<BackgroundColor>{fill}</BackgroundColor>"
    if pad:
        s += "<PaddingLeft>3pt</PaddingLeft><PaddingRight>3pt</PaddingRight><PaddingTop>2pt</PaddingTop><PaddingBottom>2pt</PaddingBottom>"
    s += "</Style>"
    return s


def textbox(name, expr, fmt=None, size="10pt", weight="Normal", color="Black", align="Left", fill=None, border=None, top=None, left=None, width=None, height=None, span=None):
    pos = "".join(f"<{k}>{v}in</{k}>" for k, v in (("Top", top), ("Left", left), ("Height", height), ("Width", width)) if v is not None)
    tf = f"<Format>{escape(fmt)}</Format>" if fmt else ""
    cell_style = style(fill=fill, border=border)
    return (f"<Textbox Name={quoteattr(name)}><CanGrow>true</CanGrow><KeepTogether>true</KeepTogether><Paragraphs><Paragraph><TextRuns><TextRun>"
            f"<Value>{escape(expr)}</Value><Style><FontFamily>{FONT}</FontFamily><FontSize>{size}</FontSize><FontWeight>{weight}</FontWeight>{tf}<Color>{color}</Color></Style>"
            f"</TextRun></TextRuns><Style><TextAlign>{align}</TextAlign></Style></Paragraph></Paragraphs>"
            f"<rd:DefaultName>{escape(name)}</rd:DefaultName>{pos}{cell_style}</Textbox>")


def cell(content, span=None):
    colspan = f"<ColSpan>{span}</ColSpan>" if span else ""
    return f"<TablixCell><CellContents>{content}{colspan}</CellContents></TablixCell>"


def empty_cells(n):
    return "".join("<TablixCell/>" for _ in range(n))


def tablix():
    ncol = len(COLS)
    cols = "".join(f"<TablixColumn><Width>{w}in</Width></TablixColumn>" for _, w in COLS)
    title = cell(textbox("StoreTitle", "=Fields!Store.Value", size="14pt", weight="Bold", color="#1F3864"), span=ncol) + empty_cells(ncol - 1)
    head = "".join(cell(textbox(f"Head{i}", h, weight="Bold", color="White", align=a, fill="#1F3864")) for i, (h, _, _, a) in enumerate(CELLS))
    detail = "".join(cell(textbox(f"Cell{i}", e, fmt=f, align=a, border="#BFBFBF")) for i, (_, e, f, a) in enumerate(CELLS))
    rows = (f"<TablixRow><Height>0.35in</Height><TablixCells>{title}</TablixCells></TablixRow>"
            f"<TablixRow><Height>0.28in</Height><TablixCells>{head}</TablixCells></TablixRow>"
            f"<TablixRow><Height>0.26in</Height><TablixCells>{detail}</TablixCells></TablixRow>")
    col_h = "".join("<TablixMember/>" for _ in COLS)
    row_h = ("<TablixMember><Group Name=\"Store\"><GroupExpressions><GroupExpression>=Fields!Store.Value</GroupExpression></GroupExpressions>"
             "<PageBreak><BreakLocation>Between</BreakLocation></PageBreak></Group>"
             "<SortExpressions><SortExpression><Value>=Fields!Store.Value</Value></SortExpression></SortExpressions>"
             "<TablixMembers>"
             "<TablixMember><KeepWithGroup>After</KeepWithGroup><RepeatOnNewPage>true</RepeatOnNewPage></TablixMember>"
             "<TablixMember><KeepWithGroup>After</KeepWithGroup><RepeatOnNewPage>true</RepeatOnNewPage></TablixMember>"
             "<TablixMember><Group Name=\"Details\"/><SortExpressions><SortExpression><Value>=Fields!MonthNumber.Value</Value></SortExpression></SortExpressions></TablixMember>"
             "</TablixMembers></TablixMember>")
    return (f"<Tablix Name=\"StatementTable\"><TablixBody><TablixColumns>{cols}</TablixColumns><TablixRows>{rows}</TablixRows></TablixBody>"
            f"<TablixColumnHierarchy><TablixMembers>{col_h}</TablixMembers></TablixColumnHierarchy>"
            f"<TablixRowHierarchy><TablixMembers>{row_h}</TablixMembers></TablixRowHierarchy>"
            f"<DataSetName>StoreSales</DataSetName><Top>0in</Top><Left>0in</Left><Height>0.89in</Height><Width>{BODY_W}in</Width>"
            f"<Style><Border><Style>None</Style></Border></Style></Tablix>")


def build() -> str:
    dax = "\n".join(l for l in DAX.read_text(encoding="utf-8").splitlines() if not l.startswith("//")).strip()
    fields = "".join(f"<Field Name=\"{n}\"><DataField>{escape(d)}</DataField><rd:TypeName>System.Object</rd:TypeName></Field>" for n, d, _, _ in FIELDS)
    header = textbox("ReportTitle", "=\"Contoso Bikes store statement \" & Parameters!Year.Value", size="9pt", color="#595959", top=0.1, left=0, width=BODY_W, height=0.3)
    footer = textbox("PageNumber", "=\"Page \" & Globals!PageNumber & \" of \" & Globals!TotalPages", size="9pt", color="#595959", align="Right", top=0.1, left=0, width=BODY_W, height=0.3)
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="{NS}" xmlns:rd="{RD}">
<AutoRefresh>0</AutoRefresh>
<DataSources><DataSource Name="ContosoSales"><ConnectionProperties><DataProvider>OLEDB-MD</DataProvider>
<ConnectString>Data Source=powerbi://api.powerbi.com/v1.0/myorg/{escape(WORKSPACE)};Initial Catalog={MODEL}</ConnectString>
<IntegratedSecurity>true</IntegratedSecurity></ConnectionProperties><rd:SecurityType>None</rd:SecurityType></DataSource></DataSources>
<DataSets><DataSet Name="StoreSales"><Query><DataSourceName>ContosoSales</DataSourceName>
<QueryParameters><QueryParameter Name="@Year"><Value>=Parameters!Year.Value</Value></QueryParameter></QueryParameters>
<CommandText>{escape(dax)}</CommandText><rd:DesignerState><QueryDefinition xmlns="http://schemas.microsoft.com/AnalysisServices/QueryDefinition"><CommandType>DAX</CommandType></QueryDefinition></rd:DesignerState></Query>
<Fields>{fields}</Fields></DataSet></DataSets>
<ReportSections><ReportSection><Body><ReportItems>{tablix()}</ReportItems><Height>0.89in</Height><Style/></Body><Width>{BODY_W}in</Width>
<Page><PageHeader><Height>0.45in</Height><PrintOnFirstPage>true</PrintOnFirstPage><PrintOnLastPage>true</PrintOnLastPage><ReportItems>{header}</ReportItems><Style/></PageHeader>
<PageFooter><Height>0.45in</Height><PrintOnFirstPage>true</PrintOnFirstPage><PrintOnLastPage>true</PrintOnLastPage><ReportItems>{footer}</ReportItems><Style/></PageFooter>
<PageHeight>{PAGE_H}in</PageHeight><PageWidth>{PAGE_W}in</PageWidth><LeftMargin>{MARGIN}in</LeftMargin><RightMargin>{MARGIN}in</RightMargin><TopMargin>{MARGIN}in</TopMargin><BottomMargin>{MARGIN}in</BottomMargin><Style/></Page>
</ReportSection></ReportSections>
<ReportParameters><ReportParameter Name="Year"><DataType>Integer</DataType><DefaultValue><Values><Value>2025</Value></Values></DefaultValue><Prompt>Year</Prompt></ReportParameter></ReportParameters>
<ReportParametersLayout><GridLayoutDefinition><NumberOfColumns>4</NumberOfColumns><NumberOfRows>2</NumberOfRows><CellDefinitions><CellDefinition><ColumnIndex>0</ColumnIndex><RowIndex>0</RowIndex><ParameterName>Year</ParameterName></CellDefinition></CellDefinitions></GridLayoutDefinition></ReportParametersLayout>
<Language>en-US</Language><rd:ReportUnitType>Inch</rd:ReportUnitType>
</Report>
"""
    return xml


def pretty(xml: str) -> str:
    from lxml import etree
    root = etree.fromstring(xml.encode("utf-8"), etree.XMLParser(remove_blank_text=True))
    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="utf-8").decode("utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = pretty(build())
    if a.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit("ContosoStoreStatement.rdl is out of date, run tools/build_rdl.py")
        print("up to date")
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT}")
