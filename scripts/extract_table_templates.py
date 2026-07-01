#!/usr/bin/env python3
"""extract_table_templates.py - 표 라이브러리 HWPX -> templates/tables/*.xml 재생성

표를 한 한글파일(all_tables_preview.hwpx)에 모아두고, 이 스크립트로 표마다
table_builder.py가 소비하는 <table-template> XML을 추출한다.
원본 HWPX가 바뀌면 이 스크립트를 다시 실행만 하면 .xml 들이 갱신된다.

표 인식 규칙
  - 각 표 바로 앞 문단을 라벨로 사용한다:  "N. 이름 - 설명"
      예) "3. budget - 예산표 (연번/사업명/내용/예산/비고, 합계행 포함)"
    · 이름 -> 출력 파일명({이름}.xml) 및 <meta><name>
    · 설명 -> <meta><description>
  - 1행은 머리행(header)
  - 표 끝에서 머리행과 같은 셀 서식(borderFill)이 연속되는 행은 합계행(summary)
  - 그 사이 행들은 본문행(body) - 대표로 첫 행만 남기고, 빌드 시 데이터 수만큼 복제된다

스타일 정규화 (스킬 정합성)
  추출한 표의 charPr/paraPr/borderFill ID는 소스 한글파일이 아니라
  templates/report/header.xml 의 표준 표 스타일로 재매핑된다. build_hwpx.py 가
  표를 항상 report 헤더와 짝짓기 때문에, 재매핑이 없으면 같은 ID 번호가 서로 다른
  서식을 가리켜 글꼴·테두리가 깨진다. 소스의 색/글꼴 디자인은 보고서 표준으로 통일.
  단, 셀의 문단 여백(paraPr 좌우 margin)은 재매핑 전에 cellMargin 으로 흡수해
  보존한다 — 한글에서 '문단 여백'으로 준 표 여백도 결과에 반영된다.

Usage:
    python scripts/extract_table_templates.py
    python scripts/extract_table_templates.py assets/all_tables_preview.hwpx
    python scripts/extract_table_templates.py -o templates/tables
    python scripts/extract_table_templates.py --dry-run
    python scripts/extract_table_templates.py --prune
"""

import argparse
import copy
import re
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from lxml import etree

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"

DEFAULT_HWPX = SKILL_DIR / "assets" / "all_tables_preview.hwpx"
DEFAULT_OUTDIR = SKILL_DIR / "templates" / "tables"

# A4 보고서 본문폭 (templates/report/section0.xml 의 secPr 여백 기준).
# 추출 표 너비가 이 값을 넘으면 보고서에서 표가 잘린다.
REPORT_BODY_WIDTH = 48190

# templates/report/header.xml 의 표준 표 스타일 ID.
# 추출 템플릿은 소스 한글파일의 ID가 아니라 항상 이 ID 공간을 따른다 —
# build_hwpx.py 가 표를 report 헤더와 짝짓기 때문.
STD_TABLE_BORDER = "4"
STD_HEADER = {"border": "9", "char": "26", "para": "18"}
STD_BODY = {"border": "10", "char": "27"}
STD_BODY_PARA = {"center": "18", "justify": "22", "left": "18", "right": "18"}
STD_SUMMARY = {"border": "9", "char": "26", "para": "18"}

# "3. budget - 예산표 (...)"  ->  ("budget", "예산표 (...)", False)
# "6. roadmap - 일자별 ... [design]" -> ("roadmap", "일자별 ...", True)
#   라벨 끝에 [design] (또는 [preserve]) 마커가 있으면 정규화를 건너뛰고
#   원본 borderFill/charPr/paraPr 디자인을 그대로 sample에 보존한다.
LABEL_RE = re.compile(
    r"^\s*\d+\s*[.)]\s*([A-Za-z][\w-]*)\s*[—–-]\s*"
    r"(.+?)(?:\s*\[(design|preserve)\])?\s*$"
)


def q(tag: str, ns: str = HP) -> str:
    """네임스페이스 Clark 표기 헬퍼: q('tbl') -> '{...paragraph}tbl'."""
    return "{%s}%s" % (ns, tag)


def read_zip_xml(hwpx: Path, inner: str):
    """HWPX(zip) 안의 XML 한 개를 파싱해 root 엘리먼트를 반환."""
    with ZipFile(hwpx) as zf:
        return etree.fromstring(zf.read(inner))


def para_text(p) -> str:
    """문단(hp:p) 안의 모든 hp:t 텍스트를 이어 붙여 반환."""
    return "".join(t.text or "" for t in p.iter(q("t"))).strip()


def parse_label(text: str):
    """'N. 이름 - 설명 [design?]' 라벨에서 (이름, 설명, preserve_design)을 추출.
    형식이 아니면 None."""
    m = LABEL_RE.match(text or "")
    if not m:
        return None
    name = m.group(1)
    desc = m.group(2).strip()
    preserve = m.group(3) is not None
    return name, desc, preserve


def build_align_map(header_root) -> dict:
    """header.xml의 paraPrIDRef -> 정렬값(소문자) 매핑. columns 메타용."""
    amap = {}
    for pp in header_root.iter(q("paraPr", HH)):
        pid = pp.get("id")
        al = pp.find(".//" + q("align", HH))
        if pid and al is not None:
            amap[pid] = (al.get("horizontal") or "").lower()
    return amap


def build_margin_map(header_root) -> dict:
    """header.xml의 paraPrIDRef -> (좌, 우) 문단 여백(HWPUNIT) 매핑.

    문단 여백(<hh:margin>의 hc:left/right)은 normalize_styles 가 paraPr를
    표준 ID로 재매핑할 때 사라지므로, 추출 시 이 값을 셀의 cellMargin 으로
    흡수한다. 그래야 한글에서 '문단 여백'으로 준 표 여백도 보존된다.
    """
    mmap = {}
    for pp in header_root.iter(q("paraPr", HH)):
        pid = pp.get("id")
        if not pid:
            continue
        margin = pp.find(".//" + q("margin", HH))
        if margin is None:
            continue
        vals = {}
        for side in ("left", "right"):
            e = margin.find(q(side, HC))
            raw = e.get("value") if e is not None else None
            try:
                vals[side] = int(raw) if raw is not None else 0
            except ValueError:
                vals[side] = 0
        if vals["left"] or vals["right"]:
            mmap[pid] = (vals["left"], vals["right"])
    return mmap


def row_sig(tr) -> tuple:
    """행의 셀별 borderFillIDRef 튜플 - 머리행/본문행/합계행 판별용 지문."""
    return tuple(tc.get("borderFillIDRef") for tc in tr.findall(q("tc")))


def _set_attrs(el, **attrs) -> None:
    """속성을 호출 순서대로 설정(직렬화 시 속성 순서 보장)."""
    for k, v in attrs.items():
        el.set(k, str(v))


def _cell_height(tr) -> str:
    tc = tr.find(q("tc"))
    csz = tc.find(q("cellSz")) if tc is not None else None
    return csz.get("height") if csz is not None else "0"


def _fold_para_margin(tc, margin_map: dict) -> None:
    """셀이 참조하는 paraPr의 좌우 문단 여백을 cellMargin 에 더한다.

    normalize_styles 가 paraPrIDRef 를 표준값으로 덮어쓰기 전에 호출해야 한다.
    """
    if not margin_map:
        return
    p = tc.find(".//" + q("p"))
    pid = p.get("paraPrIDRef") if p is not None else None
    left, right = margin_map.get(pid, (0, 0))
    if not left and not right:
        return
    cm = tc.find(q("cellMargin"))
    if cm is None:
        return
    try:
        cm.set("left", str(int(cm.get("left", "0")) + left))
        cm.set("right", str(int(cm.get("right", "0")) + right))
    except (TypeError, ValueError):
        pass


def _normalize_cell(tc, border: str, char: str, para: str) -> None:
    """셀 하나의 테두리·글자·문단 스타일 ID를 표준값으로 치환하고,
    소스에서 따라온 레이아웃 캐시(linesegarray)를 제거한다."""
    tc.set("borderFillIDRef", border)
    for run in tc.iter(q("run")):
        if run.get("charPrIDRef") is not None:
            run.set("charPrIDRef", char)
    for p in tc.iter(q("p")):
        if p.get("paraPrIDRef") is not None:
            p.set("paraPrIDRef", para)
    for ls in list(tc.iter(q("linesegarray"))):
        ls.getparent().remove(ls)


def normalize_styles(tbl, header_tr, body_tr, summary_trs,
                     align_by_col, margin_map) -> None:
    """추출한 표의 모든 스타일 ID를 report/header.xml 표준 표 스타일로 재매핑.

    소스 한글파일마다 charPr/paraPr/borderFill ID가 가리키는 서식이 다르므로,
    이 단계를 거쳐야 어떤 한글파일에서 뽑은 표든 table_builder.py +
    build_hwpx.py(report 헤더)와 정합한 .xml 이 된다.

    재매핑 직전에 각 셀의 paraPr 문단 여백을 cellMargin 으로 흡수한다 —
    그렇지 않으면 표준 paraPr 로 덮이며 좌우 여백이 사라진다.
    """
    tbl.set("borderFillIDRef", STD_TABLE_BORDER)

    for tc in header_tr.findall(q("tc")):
        _fold_para_margin(tc, margin_map)
        _normalize_cell(tc, STD_HEADER["border"],
                        STD_HEADER["char"], STD_HEADER["para"])

    for tc in body_tr.findall(q("tc")):
        _fold_para_margin(tc, margin_map)
        addr = tc.find(q("cellAddr"))
        col = addr.get("colAddr") if addr is not None else None
        align = align_by_col.get(col, "center")
        para = STD_BODY_PARA.get(align, STD_BODY_PARA["center"])
        _normalize_cell(tc, STD_BODY["border"], STD_BODY["char"], para)

    for sr in summary_trs:
        for tc in sr.findall(q("tc")):
            _fold_para_margin(tc, margin_map)
            _normalize_cell(tc, STD_SUMMARY["border"],
                            STD_SUMMARY["char"], STD_SUMMARY["para"])


def _collect_used_ids(tbl):
    """hp:tbl 안에서 참조된 borderFillIDRef / charPrIDRef / paraPrIDRef를 모은다."""
    bf, cp, pp = set(), set(), set()
    for el in tbl.iter():
        for attr, store in (
            ("borderFillIDRef", bf),
            ("charPrIDRef", cp),
            ("paraPrIDRef", pp),
        ):
            v = el.get(attr)
            if v is None:
                continue
            try:
                store.add(int(v))
            except ValueError:
                pass
    return bf, cp, pp


def extract_template_preserve_design(src_tbl, name: str, description: str,
                                      lib_header_root):
    """디자인 보존 모드: 라이브러리 원본 표를 거의 그대로 sample에 담고
    의존 bf/cp/pp 정의를 meta/extra-styles 에 자동 추출한다."""
    tbl = copy.deepcopy(src_tbl)
    rows = tbl.findall(q("tr"))
    if not rows:
        raise ValueError("행이 0개라 표로 인식할 수 없음")

    # row-type 부여: 1행 = header, 나머지 = body. summary는 자동 판정 어렵고,
    # preserve 모드에서는 build 시 sample 그대로 사용하므로 굳이 분리 불요.
    rows[0].set("row-type", "header")
    for tr in rows[1:]:
        tr.set("row-type", "body")

    # 의존 스타일 ID 수집 후 라이브러리 header.xml에서 정의 복사
    used_bf, used_cp, used_pp = _collect_used_ids(tbl)
    lib_bfs = lib_header_root.find(".//" + q("borderFills", HH))
    lib_cps = lib_header_root.find(".//" + q("charProperties", HH))
    lib_pps = lib_header_root.find(".//" + q("paraProperties", HH))

    def _pick(group, ids):
        out = []
        if group is None:
            return out
        for el in group:
            try:
                if int(el.get("id")) in ids:
                    out.append(copy.deepcopy(el))
            except (TypeError, ValueError):
                pass
        return out

    extra_bf = _pick(lib_bfs, used_bf)
    extra_cp = _pick(lib_cps, used_cp)
    extra_pp = _pick(lib_pps, used_pp)

    # 메타 정보
    sz = tbl.find(q("sz"))
    table_width = sz.get("width") if sz is not None else "0"

    columns = []
    for tc in rows[0].findall(q("tc")):
        addr = tc.find(q("cellAddr"))
        csz = tc.find(q("cellSz"))
        columns.append({
            "index": addr.get("colAddr") if addr is not None else str(len(columns)),
            "width": csz.get("width") if csz is not None else "0",
        })

    # 빌드 시 채워질 자리표시자 (build_hwpx + table_builder가 처리)
    tbl.set("id", "__TBL_ID__")
    tbl.set("rowCnt", "__ROW_CNT__")
    if sz is not None:
        sz.set("height", "__TBL_HEIGHT__")

    # <table-template> 조립
    root = etree.Element("table-template",
                          nsmap={"hp": HP, "hh": HH, "hc": HC})
    meta = etree.SubElement(root, "meta")
    etree.SubElement(meta, "name").text = name
    etree.SubElement(meta, "description").text = description
    etree.SubElement(meta, "preserve-design").text = "true"
    etree.SubElement(meta, "table-width").text = table_width

    # row-height: 각 행마다 첫 셀 height를 기록 (informational)
    rh = etree.SubElement(meta, "row-height")
    for ri, tr in enumerate(rows):
        first_tc = tr.find(q("tc"))
        csz = first_tc.find(q("cellSz")) if first_tc is not None else None
        h = csz.get("height") if csz is not None else "0"
        rh.set("header" if ri == 0 else f"body-{ri}", h)

    cols_el = etree.SubElement(meta, "columns")
    for col in columns:
        _set_attrs(etree.SubElement(cols_el, "col"),
                   index=col["index"], width=col["width"], align="center")

    extra = etree.SubElement(meta, "extra-styles")
    g_bf = etree.SubElement(extra, "border-fills")
    for el in extra_bf:
        g_bf.append(el)
    g_cp = etree.SubElement(extra, "char-prs")
    for el in extra_cp:
        g_cp.append(el)
    g_pp = etree.SubElement(extra, "para-prs")
    for el in extra_pp:
        g_pp.append(el)

    sample = etree.SubElement(root, "sample")
    sample.append(tbl)

    etree.indent(root, space="  ")
    xml = etree.tostring(root, pretty_print=True, xml_declaration=True,
                         encoding="UTF-8")
    info = {
        "rows": len(rows), "cols": len(columns),
        "header": 1, "body": len(rows) - 1, "summary": 0,
        "width": int(table_width) if str(table_width).isdigit() else 0,
        "preserve": True,
    }
    return xml, info


def extract_template(src_tbl, name: str, description: str,
                     align_map: dict, margin_map: dict):
    """원본 hp:tbl 하나를 <table-template> 엘리먼트로 변환.

    Returns: (xml_bytes, info_dict)
    """
    tbl = copy.deepcopy(src_tbl)
    rows = tbl.findall(q("tr"))
    if len(rows) < 2:
        raise ValueError("행이 2개 미만이라 머리행/본문행을 나눌 수 없음")

    header_tr = rows[0]
    header_sig = row_sig(header_tr)

    # 표 끝에서부터 머리행과 같은 서식이면 합계행(summary)으로 본다.
    summary_trs = []
    i = len(rows) - 1
    while i >= 1 and row_sig(rows[i]) == header_sig:
        summary_trs.insert(0, rows[i])
        i -= 1
    body_trs = rows[1:i + 1]
    if not body_trs:  # 본문행이 0개로 판정되면 합계행 판정을 취소한다.
        body_trs = rows[1:]
        summary_trs = []
    body_tr = body_trs[0]

    # --- 메타 정보 추출 (표 변형 전에 수행) ---
    header_h = _cell_height(header_tr)
    body_h = _cell_height(body_tr)
    summary_h = _cell_height(summary_trs[0]) if summary_trs else body_h

    sz = tbl.find(q("sz"))
    table_width = sz.get("width") if sz is not None else "0"

    columns = []
    for tc in header_tr.findall(q("tc")):
        addr = tc.find(q("cellAddr"))
        csz = tc.find(q("cellSz"))
        columns.append({
            "index": addr.get("colAddr") if addr is not None else str(len(columns)),
            "width": csz.get("width") if csz is not None else "0",
        })
    # 열 정렬값은 본문행 셀의 paraPrIDRef 기준으로 결정.
    align_by_col = {}
    for tc in body_tr.findall(q("tc")):
        addr = tc.find(q("cellAddr"))
        p = tc.find(".//" + q("p"))
        if addr is not None:
            pp = p.get("paraPrIDRef") if p is not None else None
            align_by_col[addr.get("colAddr")] = align_map.get(pp, "center")
    for col in columns:
        col["align"] = align_by_col.get(col["index"], "center")

    # --- 표를 템플릿 형태로 변형 ---
    # 머리행 + 본문 대표행 1개 + 합계행만 남긴다.
    kept = [header_tr, body_tr, *summary_trs]
    for tr in rows:
        tbl.remove(tr)
    for tr in kept:
        tbl.append(tr)

    header_tr.set("row-type", "header")
    body_tr.set("row-type", "body")
    for tr in summary_trs:
        tr.set("row-type", "summary")

    # 셀 문단 여백 흡수 + 스타일 ID 재매핑 (스킬 정합성의 핵심).
    normalize_styles(tbl, header_tr, body_tr, summary_trs, align_by_col, margin_map)

    # 빌드 시 table_builder.py가 채우는 값은 플레이스홀더로 치환.
    tbl.set("id", "__TBL_ID__")
    tbl.set("rowCnt", "__ROW_CNT__")
    if sz is not None:
        sz.set("height", "__TBL_HEIGHT__")
    for p in tbl.iter(q("p")):
        p.set("id", "__P_ID__")
    # 본문행/합계행은 행 주소를 플레이스홀더로, 셀 텍스트는 비운다.
    for tr in (body_tr, *summary_trs):
        for addr in tr.iter(q("cellAddr")):
            addr.set("rowAddr", "__ROW_ADDR__")
        for t in tr.iter(q("t")):
            t.text = None

    # --- <table-template> 조립 ---
    root = etree.Element("table-template", nsmap={"hp": HP})
    meta = etree.SubElement(root, "meta")
    etree.SubElement(meta, "name").text = name
    etree.SubElement(meta, "description").text = description
    etree.SubElement(meta, "table-width").text = table_width
    _set_attrs(etree.SubElement(meta, "row-height"),
               header=header_h, body=body_h, summary=summary_h)

    # 스타일 ID는 normalize_styles 가 표준값으로 통일했으므로 그대로 기록한다.
    styles = etree.SubElement(meta, "styles")
    _set_attrs(etree.SubElement(styles, "table-border"),
               borderFillIDRef=STD_TABLE_BORDER)
    _set_attrs(etree.SubElement(styles, "header-cell"),
               borderFillIDRef=STD_HEADER["border"],
               charPrIDRef=STD_HEADER["char"], paraPrIDRef=STD_HEADER["para"])
    _set_attrs(etree.SubElement(styles, "body-cell"),
               borderFillIDRef=STD_BODY["border"],
               charPrIDRef=STD_BODY["char"], paraPrIDRef=STD_BODY_PARA["center"])
    _set_attrs(etree.SubElement(styles, "summary-cell"),
               borderFillIDRef=STD_SUMMARY["border"],
               charPrIDRef=STD_SUMMARY["char"], paraPrIDRef=STD_SUMMARY["para"])

    cols_el = etree.SubElement(meta, "columns")
    for col in columns:
        _set_attrs(etree.SubElement(cols_el, "col"),
                   index=col["index"], width=col["width"], align=col["align"])

    sample = etree.SubElement(root, "sample")
    sample.append(tbl)

    etree.indent(root, space="  ")
    xml = etree.tostring(root, pretty_print=True, xml_declaration=True,
                         encoding="UTF-8")
    info = {
        "rows": len(rows), "cols": len(columns),
        "header": 1, "body": len(body_trs), "summary": len(summary_trs),
        "width": int(table_width) if str(table_width).isdigit() else 0,
    }
    return xml, info


def main() -> None:
    parser = argparse.ArgumentParser(
        description="표 라이브러리 HWPX에서 table-template XML 추출/재생성")
    parser.add_argument("hwpx", nargs="?", type=Path, default=DEFAULT_HWPX,
                        help="원본 HWPX 경로 (기본: assets/all_tables_preview.hwpx)")
    parser.add_argument("-o", "--output-dir", type=Path, default=DEFAULT_OUTDIR,
                        help="출력 디렉토리 (기본: templates/tables)")
    parser.add_argument("--dry-run", action="store_true",
                        help="파일을 쓰지 않고 결과만 출력")
    parser.add_argument("--prune", action="store_true",
                        help="원본 HWPX에 없는 기존 *.xml 템플릿을 삭제")
    args = parser.parse_args()

    if not args.hwpx.is_file():
        print(f"오류: HWPX 파일을 찾을 수 없음: {args.hwpx}", file=sys.stderr)
        sys.exit(1)

    try:
        section = read_zip_xml(args.hwpx, "Contents/section0.xml")
        header = read_zip_xml(args.hwpx, "Contents/header.xml")
    except BadZipFile:
        print(f"오류: 올바른 HWPX(zip)가 아님: {args.hwpx}", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        print(f"오류: HWPX 안에서 파일을 찾을 수 없음: {e}", file=sys.stderr)
        sys.exit(1)

    align_map = build_align_map(header)
    margin_map = build_margin_map(header)

    sec = section
    if not section.tag == q("sec", HS):
        found_sec = section.find(".//" + q("sec", HS))
        if found_sec is not None:
            sec = found_sec

    # 라벨 문단과 표를 짝짓는다 (표 바로 앞의 마지막 비어있지 않은 문단).
    pairs = []  # (label_text, tbl)
    pending = None
    for p in sec.findall(q("p")):
        tbls = p.findall(".//" + q("tbl"))
        if tbls:
            for tbl in tbls:
                pairs.append((pending, tbl))
            pending = None
        else:
            txt = para_text(p)
            if txt:
                pending = txt

    if not pairs:
        print("오류: HWPX 본문에서 표를 찾지 못함", file=sys.stderr)
        sys.exit(1)

    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"원본 : {args.hwpx}")
    print(f"출력 : {args.output_dir}")
    print(f"표 {len(pairs)}개 발견\n")

    generated = []
    for n, (label, tbl) in enumerate(pairs, 1):
        parsed = parse_label(label) if label else None
        preserve = False
        if parsed:
            name, desc, preserve = parsed
        else:
            name, desc = f"table{n}", (label or "").strip()
            print(f"  ! 표{n}: 라벨 해석 실패 -> 이름을 '{name}'로 지정 "
                  f"(권장 형식: 'N. 이름 - 설명')")

        try:
            if preserve:
                xml, info = extract_template_preserve_design(
                    tbl, name, desc, lib_header_root=header)
            else:
                xml, info = extract_template(tbl, name, desc,
                                              align_map, margin_map)
        except ValueError as e:
            print(f"  x 표{n} ({name}): {e}", file=sys.stderr)
            continue

        out = args.output_dir / f"{name}.xml"
        if not args.dry_run:
            out.write_bytes(xml)
        generated.append(name)
        tag = " (dry-run)" if args.dry_run else ""
        mode = " [design]" if info.get("preserve") else ""
        body_str = (str(info["body"]) if info.get("preserve")
                    else f"{info['body']}->1")
        print(f"  o {name:12s} {info['rows']}행x{info['cols']}열  "
              f"(머리 {info['header']} / 본문 {body_str} / "
              f"합계 {info['summary']}){mode}  -> {out.name}{tag}")
        if info["width"] > REPORT_BODY_WIDTH:
            print(f"    ! 경고: 표 너비 {info['width']} > 보고서 본문폭 "
                  f"{REPORT_BODY_WIDTH} — 한글에서 열 너비를 줄여 다시 추출하세요",
                  file=sys.stderr)

    # 원본 HWPX에 더 이상 없는 기존 템플릿 처리.
    existing = {p.stem for p in args.output_dir.glob("*.xml")}
    orphans = sorted(existing - set(generated))
    if orphans:
        print()
        for o in orphans:
            path = args.output_dir / f"{o}.xml"
            if args.prune and not args.dry_run:
                path.unlink()
                print(f"  - {o}.xml 삭제 (원본 HWPX에 없음)")
            else:
                hint = "dry-run" if args.dry_run else "--prune 로 삭제 가능"
                print(f"  ! {o}.xml 은 원본 HWPX에 없음 ({hint})")

    verb = "생성 예정" if args.dry_run else "생성 완료"
    print(f"\n{verb}: {len(generated)}개")


if __name__ == "__main__":
    main()
