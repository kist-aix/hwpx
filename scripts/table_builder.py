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
HH = "http://www.hancom.co.kr/hwpml/2011/head"
NS = {"hp": HP}
ROW_TYPE_ATTR = "row-type"


def is_preserve_design(root):
    """True when the template opts out of header/body/summary normalisation
    and keeps the library's original borderFill/charPr/paraPr design intact.
    Such templates carry their style definitions inline under meta/extra-styles."""
    el = root.find("meta/preserve-design")
    return el is not None and (el.text or "").strip().lower() == "true"


def merge_template_styles_into_header(template_name, header_tree):
    """Merge a preserve-design template's extra-styles into a report header.xml.

    The template's meta/extra-styles records the bf/cp/pp definitions the
    sample table relies on (with the library's original IDs). The report
    header may already hold colliding IDs for unrelated styles, so each
    library definition is appended under a fresh ID. Returns a dict of
    {bf|cp|pp: {old_id: new_id}} to feed into build_table's id_mapping arg.

    For non-preserve templates the function is a no-op (empty mapping).
    """
    template_root = load_template(template_name)
    empty = {"bf": {}, "cp": {}, "pp": {}}
    if not is_preserve_design(template_root):
        return empty
    extra = template_root.find("meta/extra-styles")
    if extra is None:
        return empty

    rep_root = header_tree.getroot()
    rep_bfs = rep_root.find(f".//{{{HH}}}borderFills")
    rep_cps = rep_root.find(f".//{{{HH}}}charProperties")
    rep_pps = rep_root.find(f".//{{{HH}}}paraProperties")

    mapping = {"bf": {}, "cp": {}, "pp": {}}

    def _merge(group_el, report_group, key):
        if group_el is None or report_group is None:
            return
        ids_present = {int(el.get("id")) for el in report_group}
        next_id = max(ids_present, default=-1) + 1
        added = 0
        for src in group_el:
            old = int(src.get("id"))
            new_el = copy.deepcopy(src)
            new_el.set("id", str(next_id))
            report_group.append(new_el)
            mapping[key][old] = next_id
            next_id += 1
            added += 1
        report_group.set("itemCnt", str(int(report_group.get("itemCnt")) + added))

    _merge(extra.find("border-fills"), rep_bfs, "bf")
    _merge(extra.find("char-prs"), rep_cps, "cp")
    _merge(extra.find("para-prs"), rep_pps, "pp")
    return mapping


def _remap_id_refs(tbl, id_mapping):
    """Walk a hp:tbl and rewrite borderFillIDRef/charPrIDRef/paraPrIDRef
    according to id_mapping = {bf|cp|pp: {old:new}}."""
    bf_map = id_mapping.get("bf", {})
    cp_map = id_mapping.get("cp", {})
    pp_map = id_mapping.get("pp", {})
    for el in tbl.iter():
        for attr, mp in (
            ("borderFillIDRef", bf_map),
            ("charPrIDRef", cp_map),
            ("paraPrIDRef", pp_map),
        ):
            v = el.get(attr)
            if v is None:
                continue
            try:
                old = int(v)
            except ValueError:
                continue
            if old in mp:
                el.set(attr, str(mp[old]))


def _set_cell_text(tc, text):
    """Replace cell text safely — clear any leftover hp:t nodes (libraries
    sometimes split a cell's text across several hp:t fragments for quote
    marks etc., so writing to only the first node leaves residue otherwise)."""
    ts = list(tc.iter(f"{{{HP}}}t"))
    if not ts:
        return
    ts[0].text = text
    for t in ts[1:]:
        t.text = None


# Shape-like elements that own a globally-unique @id in HWPX. When the same
# preserve-design sample is embedded twice in one document, these IDs (along
# with @instid wherever it appears) must be reassigned or the document will
# carry duplicate object IDs.
_SHAPE_TAGS = frozenset({
    "polygon", "rect", "line", "ellipse", "arc", "curve",
    "picture", "ole", "container", "objectGroup",
    "textart", "compose", "connectLine", "autoShape",
})


def _refresh_shape_and_inst_ids(tbl, counter):
    """Reassign @id on shape elements and any @instid attribute inside tbl.
    counter is a single-item list used as a mutable integer."""
    for el in tbl.iter():
        local = el.tag.split("}")[-1]
        if local in _SHAPE_TAGS and "id" in el.attrib:
            el.set("id", str(counter[0]))
            counter[0] += 1
        if "instid" in el.attrib:
            el.set("instid", str(counter[0]))
            counter[0] += 1


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
        # Update cellAddr — preserve original colAddr so that templates with
        # rowSpan>1 spacer cells (e.g. roadmap) keep correct horizontal
        # alignment when the body row is cloned. For ordinary templates the
        # original colAddr is already 0,1,2,... so this is a no-op.
        addr = tc.find(f"{{{HP}}}cellAddr")
        if addr is not None:
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

    # Reassign shape @id and @instid so a body-row template cloned for each
    # data row doesn't replicate the same object IDs. Current ordinary
    # templates carry no shapes so this is a no-op for them, but keeps the
    # invariant true for any future shape-bearing template.
    _refresh_shape_and_inst_ids(tr, id_counter)

    return tr


def build_table(template, data, headers=None, summary=None,
                start_id=1000000050, table_id=None, id_mapping=None):
    """Build a complete hp:tbl XML string from template + data.

    Args:
        template: Template name (e.g. "basic", "budget")
        data: List of rows, each row is list of cell strings
        headers: Optional header text override (uses template defaults if None)
        summary: Optional summary/total row data (list of strings)
        start_id: Starting ID for paragraph elements
        table_id: Explicit table element ID (defaults to start_id - 1)
        id_mapping: For preserve-design templates only — the bf/cp/pp ID
            map returned by merge_template_styles_into_header(). Ignored
            for ordinary templates.

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

    if is_preserve_design(root):
        return _build_table_preserve(
            tbl, data=data, headers=headers, summary=summary,
            start_id=start_id, table_id=table_id,
            id_mapping=id_mapping or {"bf": {}, "cp": {}, "pp": {}},
        )

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

    # Header rowSpan>1 cells (spacer pattern, e.g. roadmap) are assumed to
    # extend to the bottom of the table. Resize their rowSpan/cellSz.height
    # to match the actual final row count and total height.
    all_trs = tbl.findall(f"{{{HP}}}tr")
    body_summary_h = (num_body * body_h) + (num_summary * summary_h)
    for hr_idx in range(num_header):
        hr = all_trs[hr_idx]
        for tc in hr.findall(f"{{{HP}}}tc"):
            span = tc.find(f"{{{HP}}}cellSpan")
            if span is None or int(span.get("rowSpan", "1")) <= 1:
                continue
            span.set("rowSpan", str(total_rows - hr_idx))
            sz_cell = tc.find(f"{{{HP}}}cellSz")
            if sz_cell is not None:
                cell_h = (num_header - hr_idx) * header_h + body_summary_h
                sz_cell.set("height", str(cell_h))

    sz = tbl.find(f"{{{HP}}}sz")
    if sz is not None:
        sz.set("height", str(total_height))

    return etree.tostring(tbl, encoding="unicode")


def _build_table_preserve(tbl, data, headers, summary,
                           start_id, table_id, id_mapping):
    """Preserve-design path: keep the sample table verbatim, only remap
    style IDs and substitute cell text.

    Data shape (different from ordinary build_table):
      - `headers`: a flat list of strings sized to match every header-row cell
        (in cellAddr order, including spacer cells which take empty strings).
        When multiple header rows exist, pass a list of such lists.
      - `data`: a list whose length equals the number of body rows in the
        sample. Each item is a list of strings sized to that body row's
        cells (in order). Body rows are NOT cloned — the sample's structure
        is taken as the final structure.
      - `summary`: a flat list sized to the summary row's cells (if present).
    """
    _remap_id_refs(tbl, id_mapping)

    # Fresh table id + paragraph ids
    tbl_id = table_id if table_id is not None else start_id - 1
    tbl.set("id", str(tbl_id))
    pid = [start_id]
    for p in tbl.iter(f"{{{HP}}}p"):
        p.set("id", str(pid[0]))
        pid[0] += 1
    # Reassign shape @id and any @instid so the same preserve-design sample
    # can be embedded twice in one document without duplicate object IDs
    # (e.g. roadmap's spacer cells own 4 polygon shapes each).
    _refresh_shape_and_inst_ids(tbl, pid)

    # Safety: blank every cell first so any sample placeholder text (e.g.
    # 라이브러리 원본의 '타이틀1', '상세내용1', 일자 더미값) cannot leak
    # through when the caller's headers/data don't cover all cells.
    for tc in tbl.iter(f"{{{HP}}}tc"):
        _set_cell_text(tc, "")

    # Substitute cell text row-by-row using the row-type attribute
    body_idx = 0
    header_rows_used = 0

    def _apply_row(tr, texts):
        for ci, tc in enumerate(tr.findall(f"{{{HP}}}tc")):
            if ci < len(texts):
                _set_cell_text(tc, texts[ci])

    for tr in tbl.findall(f"{{{HP}}}tr"):
        rtype = tr.get(ROW_TYPE_ATTR, "body")
        if rtype == "header" and headers is not None:
            row_texts = headers
            if headers and isinstance(headers[0], list):
                row_texts = headers[header_rows_used] if header_rows_used < len(headers) else []
                header_rows_used += 1
            _apply_row(tr, row_texts)
        elif rtype == "body" and data is not None:
            if body_idx < len(data):
                _apply_row(tr, data[body_idx])
                body_idx += 1
        elif rtype == "summary" and summary is not None:
            _apply_row(tr, summary)
        if ROW_TYPE_ATTR in tr.attrib:
            del tr.attrib[ROW_TYPE_ATTR]

    # Update table rowCnt (in case any sample placeholder was left)
    tbl.set("rowCnt", str(len(tbl.findall(f"{{{HP}}}tr"))))
    # Recompute table height from per-row cellSz heights of the first cell
    total_h = 0
    for tr in tbl.findall(f"{{{HP}}}tr"):
        first_tc = tr.find(f"{{{HP}}}tc")
        if first_tc is None:
            continue
        sz_cell = first_tc.find(f"{{{HP}}}cellSz")
        if sz_cell is None:
            continue
        try:
            total_h += int(sz_cell.get("height", "0"))
        except ValueError:
            pass
    sz = tbl.find(f"{{{HP}}}sz")
    if sz is not None and total_h:
        sz.set("height", str(total_h))

    return etree.tostring(tbl, encoding="unicode")


def build_table_paragraph(template, data, headers=None, summary=None,
                          start_id=1000000050, id_mapping=None):
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
        id_mapping=id_mapping,
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
