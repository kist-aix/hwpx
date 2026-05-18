#!/usr/bin/env python3
"""Build HWPX table XML from templates and data.

Usage as module:
    from table_builder import build_table, build_table_paragraph
    xml = build_table("basic", data=[["1","A","B","C"]], start_id=50)

Usage as CLI:
    python table_builder.py --template basic --data '[["1","A","B","C"]]' --start-id 50
    python table_builder.py --list
"""

import argparse
import copy
import json
import sys
from pathlib import Path
from lxml import etree

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR.parent / "templates" / "tables"

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS = {"hp": HP}
ROW_TYPE_ATTR = "row-type"


def list_templates():
    """Return available template names with descriptions."""
    templates = []
    for p in sorted(TEMPLATES_DIR.glob("*.xml")):
        try:
            root = etree.parse(str(p)).getroot()
            meta = root.find("meta")
            name = meta.findtext("name", p.stem) if meta is not None else p.stem
            desc = meta.findtext("description", "") if meta is not None else ""
            templates.append((name, desc))
        except Exception:
            templates.append((p.stem, "(parse error)"))
    return templates


def load_template(name):
    """Load and parse a table template XML file."""
    path = TEMPLATES_DIR / f"{name}.xml"
    if not path.is_file():
        available = [t[0] for t in list_templates()]
        raise FileNotFoundError(
            f"Template '{name}' not found. Available: {', '.join(available)}"
        )
    return etree.parse(str(path)).getroot()


def _find_tbl(sample):
    """Find hp:tbl element in sample, handling namespace variations."""
    tbl = sample.find(f"{{{HP}}}tbl")
    if tbl is None:
        tbl = sample.find("hp:tbl", NS)
    if tbl is None:
        for child in sample:
            if child.tag.endswith("}tbl") or child.tag == "hp:tbl":
                tbl = child
                break
    return tbl


def _extract_row_text(tr):
    """Extract text from each cell in a row."""
    texts = []
    for tc in tr.findall(f"{{{HP}}}tc"):
        t = tc.find(f".//{{{HP}}}t")
        texts.append(t.text if t is not None and t.text else "")
    return texts


def _process_row(tr, row_data, row_addr, id_counter):
    """Fill a row template with data, update IDs and addresses."""
    tr = copy.deepcopy(tr)

    # Remove custom row-type attribute
    if ROW_TYPE_ATTR in tr.attrib:
        del tr.attrib[ROW_TYPE_ATTR]

    cells = tr.findall(f"{{{HP}}}tc")
    for col_idx, tc in enumerate(cells):
        # Update cellAddr
        addr = tc.find(f"{{{HP}}}cellAddr")
        if addr is not None:
            addr.set("colAddr", str(col_idx))
            addr.set("rowAddr", str(row_addr))

        # Update paragraph IDs
        for p in tc.findall(f".//{{{HP}}}p"):
            p.set("id", str(id_counter[0]))
            id_counter[0] += 1

        # Update text content
        text = row_data[col_idx] if col_idx < len(row_data) else ""
        t_elem = tc.find(f".//{{{HP}}}t")
        if t_elem is not None:
            t_elem.text = text
        else:
            # Create hp:t element if missing
            run = tc.find(f".//{{{HP}}}run")
            if run is not None:
                t_elem = etree.SubElement(run, f"{{{HP}}}t")
                t_elem.text = text

    return tr


def build_table(template, data, headers=None, summary=None,
                start_id=1000000050, table_id=None):
    """Build a complete hp:tbl XML string from template + data.

    Args:
        template: Template name (e.g. "basic", "budget")
        data: List of rows, each row is list of cell strings
        headers: Optional header text override (uses template defaults if None)
        summary: Optional summary/total row data (list of strings)
        start_id: Starting ID for paragraph elements
        table_id: Explicit table element ID (defaults to start_id - 1)

    Returns:
        XML string of the complete hp:tbl element
    """
    root = load_template(template)
    sample = root.find("sample")
    if sample is None:
        raise ValueError(f"Template '{template}' has no <sample> element")

    tbl = _find_tbl(sample)
    if tbl is None:
        raise ValueError(f"Template '{template}' has no hp:tbl in <sample>")

    tbl = copy.deepcopy(tbl)

    # Classify rows by type
    header_rows = []
    body_row_template = None
    summary_row_templates = []

    for tr in list(tbl.findall(f"{{{HP}}}tr")):
        row_type = tr.get(ROW_TYPE_ATTR, "body")
        if row_type == "header":
            header_rows.append(tr)
        elif row_type == "body":
            body_row_template = tr
        elif row_type == "summary":
            summary_row_templates.append(tr)
        tbl.remove(tr)

    if body_row_template is None:
        raise ValueError(f"Template '{template}' has no body row (row-type='body')")

    # ID management
    id_counter = [start_id]
    tbl_id = table_id if table_id is not None else start_id - 1

    row_addr = 0

    # 1. Header rows
    for hr in header_rows:
        if headers:
            hr = _process_row(hr, headers, row_addr, id_counter)
        else:
            hr = _process_row(hr, _extract_row_text(hr), row_addr, id_counter)
        tbl.append(hr)
        row_addr += 1

    # 2. Data rows (clone body template for each)
    for row_data in data:
        tr = _process_row(body_row_template, row_data, row_addr, id_counter)
        tbl.append(tr)
        row_addr += 1

    # 3. Summary rows
    if summary and summary_row_templates:
        for sr in summary_row_templates:
            sr = _process_row(sr, summary, row_addr, id_counter)
            tbl.append(sr)
            row_addr += 1

    # Update table attributes
    total_rows = row_addr
    tbl.set("id", str(tbl_id))
    tbl.set("rowCnt", str(total_rows))

    # Calculate total height from meta
    meta = root.find("meta")
    row_heights = meta.find("row-height") if meta is not None else None
    header_h = int(row_heights.get("header", "2363")) if row_heights is not None else 2363
    body_h = int(row_heights.get("body", "1984")) if row_heights is not None else 1984
    summary_h = int(row_heights.get("summary", "1984")) if row_heights is not None else 1984

    num_header = len(header_rows)
    num_body = len(data)
    num_summary = len(summary_row_templates) if summary else 0
    total_height = (num_header * header_h) + (num_body * body_h) + (num_summary * summary_h)

    sz = tbl.find(f"{{{HP}}}sz")
    if sz is not None:
        sz.set("height", str(total_height))

    return etree.tostring(tbl, encoding="unicode")


def build_table_paragraph(template, data, headers=None, summary=None,
                          start_id=1000000050):
    """Build a complete <hp:p> wrapping <hp:tbl>, ready for section0.xml.

    Returns XML string of hp:p element containing the table.
    """
    table_xml = build_table(
        template=template,
        data=data,
        headers=headers,
        summary=summary,
        start_id=start_id + 1,
        table_id=start_id,
    )

    wrapper = (
        f'<hp:p xmlns:hp="{HP}" '
        f'id="{start_id}" paraPrIDRef="2" styleIDRef="0" '
        f'pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="27">'
        f'{table_xml}'
        f'<hp:t/>'
        f'</hp:run>'
        f'</hp:p>'
    )
    return wrapper


def main():
    parser = argparse.ArgumentParser(description="Build HWPX table XML from templates")
    parser.add_argument("--template", "-t", help="Template name")
    parser.add_argument("--data", "-d", help="JSON array of rows: [[\"a\",\"b\"],[\"c\",\"d\"]]")
    parser.add_argument("--headers", help="JSON array of header texts (optional)")
    parser.add_argument("--summary", help="JSON array of summary row texts (optional)")
    parser.add_argument("--start-id", type=int, default=1000000050, help="Starting paragraph ID")
    parser.add_argument("--paragraph", "-p", action="store_true",
                        help="Output wrapped in hp:p (ready for section0.xml)")
    parser.add_argument("--list", "-l", action="store_true", help="List available templates")
    args = parser.parse_args()

    if args.list:
        templates = list_templates()
        if not templates:
            print("No templates found in", TEMPLATES_DIR)
        else:
            print("Available table templates:")
            for name, desc in templates:
                print(f"  {name:15s}  {desc}")
        return

    if not args.template or not args.data:
        parser.error("--template and --data are required (or use --list)")

    data = json.loads(args.data)
    headers = json.loads(args.headers) if args.headers else None
    summary = json.loads(args.summary) if args.summary else None

    if args.paragraph:
        result = build_table_paragraph(
            template=args.template, data=data, headers=headers,
            summary=summary, start_id=args.start_id,
        )
    else:
        result = build_table(
            template=args.template, data=data, headers=headers,
            summary=summary, start_id=args.start_id,
        )

    print(result)


if __name__ == "__main__":
    main()
