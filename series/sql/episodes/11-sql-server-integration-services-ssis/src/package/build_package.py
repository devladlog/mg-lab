"""Writes PartnerSalesLoad.dtsx, the SSIS package of episode 11 (SQL Server 2022, project deployment model).

    python src/package/build_package.py            # rewrites src/package/PartnerSalesLoad.dtsx
    python src/package/build_package.py --check    # exit 1 when the file on disk differs from what this writes

Why a generator: a .dtsx is XML in which every data flow column repeats its lineage id in four or five places.
One table of columns (COLUMNS) below drives the flat file connection manager, the source, the Conditional Split
and both destinations, so they cannot drift apart. All GUIDs are derived (uuid5) so the output is deterministic.

HONEST LIMIT: nothing in the build container can open or run a package (no SSIS, Windows only). The file is
checked by tests/test_package.py for well-formed XML, unique ids, every reference resolving, column names and types
agreeing with the SQL tables and the Conditional Split rule evaluated on the sample files. The first real
open in Visual Studio and run on CON-SQL01 is part of the recording (demo.md).
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

OUT = Path(__file__).with_name("PartnerSalesLoad.dtsx")
NS = uuid.UUID("6f1c2f0e-0000-4000-8000-000000000011")   # fixed namespace for the derived GUIDs
PKG = "PartnerSalesLoad"
DF = "Load partner file"                                # the Data Flow Task
DF_REF = f"Package\\{DF}"


def guid(name: str) -> str:
    return "{" + str(uuid.uuid5(NS, name)).upper() + "}"


# name, flat file type (DTS:DataType), SSIS pipeline type, length, precision, scale, SQL type of Stg.PartnerSales
COLUMNS = [
    ("DealerCode",      130, "wstr",    10, 0, 0, "nvarchar(10)"),
    ("PartnerOrderRef", 130, "wstr",    20, 0, 0, "nvarchar(20)"),
    ("LineNumber",        3, "i4",       0, 0, 0, "int"),
    ("SaleDate",        133, "dbDate",   0, 0, 0, "date"),
    ("ProductId",         3, "i4",       0, 0, 0, "int"),
    ("Quantity",          3, "i4",       0, 0, 0, "int"),
    ("UnitPrice",       131, "numeric",  0, 10, 2, "decimal(10,2)"),
]
VALID_RULE = "Quantity > 0 && UnitPrice >= 0"           # the Conditional Split condition (SSIS expression language)
PARAMS = [  # name, SSIS data type number (8 = String), default
    ("InputFile", 8, r"C:\MGLab\ssis\in\partner-sales-2025-05-21.csv"),
    ("ServerName", 8, "localhost"),
]
CM_DB, CM_FILE = "ContosoBikesEtl", "PartnerFile"
SERVER_EXECUTION_ID = "(DT_WSTR, 20) @[System::ServerExecutionID]"
INPUT_FILE_SQL = 'REPLACE(@[$Package::InputFile], "\'", "\'\'")'   # doubles single quotes inside the T-SQL literal
PREPARE_EXPR = (f'"EXEC Etl.usp_PrepareLoad @ExecutionId = " + {SERVER_EXECUTION_ID} + ", @SourceFile = N\'" + {INPUT_FILE_SQL} + "\'"')
MERGE_EXPR = f'"EXEC Etl.usp_MergePartnerSales @ExecutionId = " + {SERVER_EXECUTION_ID}'
PREPARE_DEFAULT = "EXEC Etl.usp_PrepareLoad @ExecutionId = 0, @SourceFile = N''"
MERGE_DEFAULT = "EXEC Etl.usp_MergePartnerSales @ExecutionId = 0"
CONN_EXPR = ('"Data Source=" + @[$Package::ServerName] + ";Initial Catalog=' + CM_DB +
             ';Provider=MSOLEDBSQL19;Integrated Security=SSPI;Application Name=' + PKG +
             ';Encrypt=Mandatory;TrustServerCertificate=yes;"')
CONN_DEFAULT = (f"Data Source=localhost;Initial Catalog={CM_DB};Provider=MSOLEDBSQL19;Integrated Security=SSPI;"
                f"Application Name={PKG};Encrypt=Mandatory;TrustServerCertificate=yes;")
SSIS_CONTACT = "Microsoft Corporation; Microsoft SQL Server; (C) Microsoft Corporation; All Rights Reserved; http://www.microsoft.com/sql/support/default.asp;1"


def a(v) -> str:
    return quoteattr(str(v))


def lineage(comp: str, output: str, col: str) -> str:
    return f"{DF_REF}\\{comp}.Outputs[{output}].Columns[{col}]"


def flat_file_cm() -> str:
    cols = []
    for i, (n, ft, _, ln, pr, sc, _) in enumerate(COLUMNS):
        last = i == len(COLUMNS) - 1
        extra = ""
        if ft == 130:
            extra = f' DTS:MaximumWidth="{ln}"'
        elif ft == 131:
            extra = f' DTS:DataPrecision="{pr}" DTS:DataScale="{sc}"'
        cols.append(
            f'<DTS:FlatFileColumn DTS:ColumnType="Delimited" DTS:ColumnDelimiter="{"_x000D__x000A_" if last else ","}"'
            f' DTS:TextQualified="True" DTS:ObjectName={a(n)} DTS:DTSID="{guid("ffcol-" + n)}" DTS:CreationName=""'
            f' DTS:DataType="{ft}"{extra} />')
    return f'''    <DTS:ConnectionManager DTS:refId="Package.ConnectionManagers[{CM_FILE}]" DTS:CreationName="FLATFILE" DTS:DTSID="{guid("cm-file")}" DTS:ObjectName="{CM_FILE}">
      <DTS:PropertyExpression DTS:Name="ConnectionString">@[$Package::InputFile]</DTS:PropertyExpression>
      <DTS:ObjectData>
        <DTS:ConnectionManager DTS:Format="Delimited" DTS:LocaleID="1033" DTS:HeaderRowDelimiter="_x000D__x000A_" DTS:ColumnNamesInFirstDataRow="True" DTS:RowDelimiter="" DTS:TextQualifier="_x0022_" DTS:CodePage="65001" DTS:ConnectionString={a(PARAMS[0][2])}>
          <DTS:FlatFileColumns>
            {chr(10).join("            " + c for c in cols).lstrip()}
          </DTS:FlatFileColumns>
        </DTS:ConnectionManager>
      </DTS:ObjectData>
    </DTS:ConnectionManager>
    <DTS:ConnectionManager DTS:refId="Package.ConnectionManagers[{CM_DB}]" DTS:CreationName="OLEDB" DTS:DTSID="{guid("cm-db")}" DTS:ObjectName="{CM_DB}">
      <DTS:PropertyExpression DTS:Name="ConnectionString">{escape(CONN_EXPR)}</DTS:PropertyExpression>
      <DTS:ObjectData>
        <DTS:ConnectionManager DTS:ConnectionString={a(CONN_DEFAULT)} />
      </DTS:ObjectData>
    </DTS:ConnectionManager>'''


def sql_task(name: str, expr: str, default: str, ident: str) -> str:
    return f'''    <DTS:Executable DTS:refId="Package\\{name}" DTS:CreationName="Microsoft.ExecuteSQLTask" DTS:Description="Execute SQL Task" DTS:DTSID="{guid(ident)}" DTS:ExecutableType="Microsoft.ExecuteSQLTask" DTS:LocaleID="-1" DTS:ObjectName={a(name)} DTS:ThreadHint="0">
      <DTS:Variables />
      <DTS:PropertyExpression DTS:Name="SqlStatementSource">{escape(expr)}</DTS:PropertyExpression>
      <DTS:ObjectData>
        <SQLTask:SqlTaskData xmlns:SQLTask="www.microsoft.com/sqlserver/dts/tasks/sqltask" SQLTask:Connection="{guid("cm-db")}" SQLTask:SqlStatementSource={a(default)} />
      </DTS:ObjectData>
    </DTS:Executable>'''


# ---------------------------------------------------------------- data flow
def type_attrs(ln, pr, sc, dt) -> str:
    s = f' dataType="{dt}"'
    if dt == "wstr":
        s += f' length="{ln}"'
    if dt == "numeric":
        s += f' precision="{pr}" scale="{sc}"'
    return s


def source_component() -> str:
    comp, out = "Flat File Source", "Flat File Source Output"
    base = f"{DF_REF}\\{comp}"
    ocols, ext = [], []
    for n, ft, dt, ln, pr, sc, _ in COLUMNS:
        ta = type_attrs(ln, pr, sc, dt)
        ocols.append(f'''                <outputColumn refId="{base}.Outputs[{out}].Columns[{n}]" errorOrTruncationOperation="Conversion" errorRowDisposition="FailComponent" externalMetadataColumnId="{base}.Outputs[{out}].ExternalColumns[{n}]" lineageId="{lineage(comp, out, n)}" name="{n}" truncationRowDisposition="FailComponent"{ta}>
                  <properties>
                    <property dataType="System.Boolean" description="Indicates whether the column uses the faster, locale-neutral parsing routines." name="FastParse">false</property>
                    <property dataType="System.Boolean" description="Indicates whether the data is in binary format." name="UseBinaryFormat">false</property>
                  </properties>
                </outputColumn>''')
        ext.append(f'                <externalMetadataColumn refId="{base}.Outputs[{out}].ExternalColumns[{n}]" name="{n}"{ta} />')
    nl = "\n"
    return f'''        <component refId="{base}" componentClassID="Microsoft.FlatFileSource" contactInfo="Flat File Source;{SSIS_CONTACT}" description="Flat File Source" localeId="1033" name="{comp}" usesDispositions="true" version="1">
          <properties>
            <property dataType="System.Boolean" description="Specifies whether zero-length columns are treated as null." name="RetainNulls">false</property>
            <property dataType="System.String" description="Specifies the name of an output column containing the file name. If no name is specified, no output column containing the file name will be generated." name="FileNameColumnName"></property>
          </properties>
          <connections>
            <connection refId="{base}.Connections[FlatFileConnection]" connectionManagerID="Package.ConnectionManagers[{CM_FILE}]" connectionManagerRefId="Package.ConnectionManagers[{CM_FILE}]" name="FlatFileConnection" />
          </connections>
          <outputs>
            <output refId="{base}.Outputs[{out}]" name="{out}">
              <outputColumns>
{nl.join(ocols)}
              </outputColumns>
              <externalMetadataColumns isUsed="True">
{nl.join(ext)}
              </externalMetadataColumns>
            </output>
            <output refId="{base}.Outputs[Flat File Source Error Output]" isErrorOut="true" name="Flat File Source Error Output">
              <outputColumns>
                <outputColumn refId="{base}.Outputs[Flat File Source Error Output].Columns[Flat File Source Error Output Column]" codePage="65001" dataType="text" lineageId="{base}.Outputs[Flat File Source Error Output].Columns[Flat File Source Error Output Column]" name="Flat File Source Error Output Column" />
                <outputColumn refId="{base}.Outputs[Flat File Source Error Output].Columns[ErrorCode]" dataType="i4" lineageId="{base}.Outputs[Flat File Source Error Output].Columns[ErrorCode]" name="ErrorCode" specialFlags="1" />
                <outputColumn refId="{base}.Outputs[Flat File Source Error Output].Columns[ErrorColumn]" dataType="i4" lineageId="{base}.Outputs[Flat File Source Error Output].Columns[ErrorColumn]" name="ErrorColumn" specialFlags="2" />
              </outputColumns>
              <externalMetadataColumns />
            </output>
          </outputs>
        </component>'''


def split_expression() -> str:
    """VALID_RULE with each column name replaced by its #{lineage} form, which is how a .dtsx stores it."""
    import re
    return re.sub(r"\b(" + "|".join(c[0] for c in COLUMNS) + r")\b",
                  lambda m: "#{" + lineage("Flat File Source", "Flat File Source Output", m.group(1)) + "}", VALID_RULE)


def split_component() -> str:
    comp, inp = "Conditional Split", "Conditional Split Input"
    base = f"{DF_REF}\\{comp}"
    icols, ext = [], []
    for n, ft, dt, ln, pr, sc, _ in COLUMNS:
        icols.append(f'                <inputColumn refId="{base}.Inputs[{inp}].Columns[{n}]" cachedDataType="{dt}"{(" cachedLength=" + a(ln)) if dt == "wstr" else ""}{(" cachedPrecision=" + a(pr) + " cachedScale=" + a(sc)) if dt == "numeric" else ""} cachedName="{n}" lineageId="{lineage("Flat File Source", "Flat File Source Output", n)}" />')
    nl = "\n"
    return f'''        <component refId="{base}" componentClassID="Microsoft.ConditionalSplit" contactInfo="Conditional Split;{SSIS_CONTACT}" description="Routes data rows to different outputs depending on the content of the data." name="{comp}" usesDispositions="true" version="0">
          <inputs>
            <input refId="{base}.Inputs[{inp}]" name="{inp}">
              <inputColumns>
{nl.join(icols)}
              </inputColumns>
              <externalMetadataColumns />
            </input>
          </inputs>
          <outputs>
            <output refId="{base}.Outputs[Valid rows]" exclusionGroup="1" name="Valid rows" synchronousInputId="{base}.Inputs[{inp}]">
              <properties>
                <property dataType="System.Int32" description="Specifies the position of the condition in the evaluation order. The position is relative to other outputs." name="EvaluationOrder">0</property>
                <property containsID="true" dataType="System.String" description="Specifies the expression to evaluate. The expression must evaluate to a Boolean." name="Expression" expressionType="Notify">{escape(split_expression())}</property>
                <property containsID="true" dataType="System.String" description="Specifies the friendly version of the expression. The friendly expression is displayed in the user interface." name="FriendlyExpression" expressionType="Notify">{escape(VALID_RULE)}</property>
              </properties>
              <outputColumns />
              <externalMetadataColumns />
            </output>
            <output refId="{base}.Outputs[Rejected rows]" exclusionGroup="1" isDefaultOut="true" name="Rejected rows" synchronousInputId="{base}.Inputs[{inp}]">
              <outputColumns />
              <externalMetadataColumns />
            </output>
            <output refId="{base}.Outputs[Conditional Split Error Output]" exclusionGroup="1" isErrorOut="true" name="Conditional Split Error Output" synchronousInputId="{base}.Inputs[{inp}]">
              <outputColumns>
                <outputColumn refId="{base}.Outputs[Conditional Split Error Output].Columns[ErrorCode]" dataType="i4" lineageId="{base}.Outputs[Conditional Split Error Output].Columns[ErrorCode]" name="ErrorCode" specialFlags="1" />
                <outputColumn refId="{base}.Outputs[Conditional Split Error Output].Columns[ErrorColumn]" dataType="i4" lineageId="{base}.Outputs[Conditional Split Error Output].Columns[ErrorColumn]" name="ErrorColumn" specialFlags="2" />
              </outputColumns>
              <externalMetadataColumns />
            </output>
          </outputs>
        </component>'''


def destination(comp: str, table: str) -> str:
    inp = "OLE DB Destination Input"
    base = f"{DF_REF}\\{comp}"
    icols, ext = [], []
    for n, ft, dt, ln, pr, sc, _ in COLUMNS:
        ta = type_attrs(ln, pr, sc, dt)
        icols.append(f'                <inputColumn refId="{base}.Inputs[{inp}].Columns[{n}]" cachedDataType="{dt}"{(" cachedLength=" + a(ln)) if dt == "wstr" else ""}{(" cachedPrecision=" + a(pr) + " cachedScale=" + a(sc)) if dt == "numeric" else ""} cachedName="{n}" externalMetadataColumnId="{base}.Inputs[{inp}].ExternalColumns[{n}]" lineageId="{lineage("Flat File Source", "Flat File Source Output", n)}" />')
        ext.append(f'                <externalMetadataColumn refId="{base}.Inputs[{inp}].ExternalColumns[{n}]" {ta.strip()} name="{n}" />')
    nl = "\n"
    return f'''        <component refId="{base}" componentClassID="Microsoft.OLEDBDestination" contactInfo="OLE DB Destination;{SSIS_CONTACT};4" description="OLE DB Destination" name={a(comp)} usesDispositions="true" version="4">
          <properties>
            <property dataType="System.Int32" description="The number of seconds before a command times out.  A value of 0 indicates an infinite time-out." name="CommandTimeout">0</property>
            <property dataType="System.String" description="Specifies the name of the database object used to open a rowset." name="OpenRowset">{escape(table)}</property>
            <property dataType="System.String" description="Specifies the variable that contains the name of the database object used to open a rowset." name="OpenRowsetVariable"></property>
            <property dataType="System.String" description="The SQL command to be executed." name="SqlCommand" UITypeEditor="Microsoft.DataTransformationServices.Controls.ModalMultilineStringEditor, Microsoft.DataTransformationServices.Controls, Version=16.0.0.0, Culture=neutral, PublicKeyToken=89845dcd8080cc91"></property>
            <property dataType="System.Int32" description="Specifies the column code page to use when code page information is unavailable from the data source." name="DefaultCodePage">1252</property>
            <property dataType="System.Boolean" description="Forces the use of the DefaultCodePage property value when describing character data." name="AlwaysUseDefaultCodePage">false</property>
            <property dataType="System.Int32" description="Specifies the mode used to access the database." name="AccessMode" typeConverter="AccessMode">3</property>
            <property dataType="System.Boolean" description="Indicates whether the values supplied for identity columns will be copied to the destination. If false, values for identity columns will be auto-generated at the destination. Applies only if fast load is turned on." name="FastLoadKeepIdentity">false</property>
            <property dataType="System.Boolean" description="Indicates whether the columns containing null will have null inserted in the destination. If false, columns containing null will have their default values inserted at the destination. Applies only if fast load is turned on." name="FastLoadKeepNulls">false</property>
            <property dataType="System.String" description="Specifies options to be used with fast load.  Applies only if fast load is turned on." name="FastLoadOptions">TABLOCK,CHECK_CONSTRAINTS</property>
            <property dataType="System.Int32" description="Specifies when commits are issued during data insertion.  A value of 0 specifies that one commit will be issued at the end of data insertion.  Applies only if fast load is turned on." name="FastLoadMaxInsertCommitSize">2147483647</property>
          </properties>
          <connections>
            <connection refId="{base}.Connections[OleDbConnection]" connectionManagerID="Package.ConnectionManagers[{CM_DB}]" connectionManagerRefId="Package.ConnectionManagers[{CM_DB}]" description="The OLE DB runtime connection used to access the database." name="OleDbConnection" />
          </connections>
          <inputs>
            <input refId="{base}.Inputs[{inp}]" errorOrTruncationOperation="Insert" errorRowDisposition="FailComponent" hasSideEffects="true" name="{inp}">
              <inputColumns>
{nl.join(icols)}
              </inputColumns>
              <externalMetadataColumns isUsed="True">
{nl.join(ext)}
              </externalMetadataColumns>
            </input>
          </inputs>
          <outputs>
            <output refId="{base}.Outputs[OLE DB Destination Error Output]" exclusionGroup="1" isErrorOut="true" name="OLE DB Destination Error Output" synchronousInputId="{base}.Inputs[{inp}]">
              <outputColumns>
                <outputColumn refId="{base}.Outputs[OLE DB Destination Error Output].Columns[ErrorCode]" dataType="i4" lineageId="{base}.Outputs[OLE DB Destination Error Output].Columns[ErrorCode]" name="ErrorCode" specialFlags="1" />
                <outputColumn refId="{base}.Outputs[OLE DB Destination Error Output].Columns[ErrorColumn]" dataType="i4" lineageId="{base}.Outputs[OLE DB Destination Error Output].Columns[ErrorColumn]" name="ErrorColumn" specialFlags="2" />
              </outputColumns>
              <externalMetadataColumns />
            </output>
          </outputs>
        </component>'''


def paths() -> str:
    src, split = f"{DF_REF}\\Flat File Source", f"{DF_REF}\\Conditional Split"
    items = [
        ("Flat File Source Output", f"{src}.Outputs[Flat File Source Output]", f"{split}.Inputs[Conditional Split Input]"),
        ("Valid rows", f"{split}.Outputs[Valid rows]", f"{DF_REF}\\Staging table.Inputs[OLE DB Destination Input]"),
        ("Rejected rows", f"{split}.Outputs[Rejected rows]", f"{DF_REF}\\Rejected rows table.Inputs[OLE DB Destination Input]"),
    ]
    return "\n".join(f'        <path refId="{DF_REF}.Paths[{n}]" endId="{e}" name="{n}" startId="{s}" />' for n, s, e in items)


def build() -> str:
    params = "\n".join(
        f'''    <DTS:PackageParameter DTS:CreationName="" DTS:DataType="{dt}" DTS:Description={a(desc)} DTS:DTSID="{guid("param-" + n)}" DTS:ObjectName="{n}">
      <DTS:Property DTS:DataType="{dt}" DTS:Name="ParameterValue">{escape(default)}</DTS:Property>
    </DTS:PackageParameter>'''
        for (n, dt, default), desc in zip(PARAMS, ["Full path of the partner CSV file, on the machine that runs the package",
                                                   "SQL Server that holds ContosoBikesEtl (localhost on CON-SQL01)"]))
    return f'''<?xml version="1.0"?>
<DTS:Executable xmlns:DTS="www.microsoft.com/SqlServer/Dts"
  DTS:refId="Package"
  DTS:CreationName="Microsoft.Package"
  DTS:DTSID="{guid("package")}"
  DTS:ExecutableType="Microsoft.Package"
  DTS:LocaleID="1033"
  DTS:ObjectName="{PKG}"
  DTS:PackageType="5"
  DTS:VersionBuild="1"
  DTS:VersionGUID="{guid("version-1")}">
  <DTS:Property DTS:Name="PackageFormatVersion">8</DTS:Property>
  <DTS:ConnectionManagers>
{flat_file_cm()}
  </DTS:ConnectionManagers>
  <DTS:PackageParameters>
{params}
  </DTS:PackageParameters>
  <DTS:Variables />
  <DTS:Executables>
{sql_task("Prepare load", PREPARE_EXPR, PREPARE_DEFAULT, "task-prepare")}
    <DTS:Executable DTS:refId="{DF_REF}" DTS:CreationName="Microsoft.Pipeline" DTS:Description="Data Flow Task" DTS:DTSID="{guid("task-dataflow")}" DTS:ExecutableType="Microsoft.Pipeline" DTS:LocaleID="-1" DTS:ObjectName="{DF}" DTS:TaskContact="Performs high-performance data extraction, transformation and loading;Microsoft Corporation; Microsoft SQL Server; (C) Microsoft Corporation; All Rights Reserved;http://www.microsoft.com/sql/support/default.asp;1">
      <DTS:Variables />
      <DTS:ObjectData>
        <pipeline version="1">
          <components>
{source_component()}
{split_component()}
{destination("Staging table", "[Stg].[PartnerSales]")}
{destination("Rejected rows table", "[Etl].[RejectedRows]")}
          </components>
          <paths>
{paths()}
          </paths>
        </pipeline>
      </DTS:ObjectData>
    </DTS:Executable>
{sql_task("Merge into Sales.PartnerSales", MERGE_EXPR, MERGE_DEFAULT, "task-merge")}
  </DTS:Executables>
  <DTS:PrecedenceConstraints>
    <DTS:PrecedenceConstraint DTS:refId="Package.PrecedenceConstraints[Constraint]" DTS:CreationName="" DTS:DTSID="{guid("pc-1")}" DTS:From="Package\\Prepare load" DTS:LogicalAnd="True" DTS:ObjectName="Constraint" DTS:To="{DF_REF}" />
    <DTS:PrecedenceConstraint DTS:refId="Package.PrecedenceConstraints[Constraint 1]" DTS:CreationName="" DTS:DTSID="{guid("pc-2")}" DTS:From="{DF_REF}" DTS:LogicalAnd="True" DTS:ObjectName="Constraint 1" DTS:To="Package\\Merge into Sales.PartnerSales" />
  </DTS:PrecedenceConstraints>
</DTS:Executable>
'''


if __name__ == "__main__":
    text = build()
    if "--check" in sys.argv:
        sys.exit(0 if OUT.exists() and OUT.read_text(encoding="utf-8") == text else 1)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({len(text)} bytes)")
