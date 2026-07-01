#!/usr/bin/env python3
"""표 템플릿을 한글(HWPX)로 미리보기할 수 있는 파일로 변환.

templates/tables/ 의 표 템플릿에 샘플 데이터를 채워
한글에서 바로 열어볼 수 있는 .hwpx 파일을 생성한다.

Usage:
    # 단일 템플릿 미리보기
    python preview_table.py basic
    python preview_table.py budget --output ~/Desktop/budget_preview.hwpx

    # 전체 템플릿 미리보기 (한 번에 모두 생성)
    python preview_table.py --all

    # 사용 가능한 템플릿 목록
    python preview_table.py --list
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
# 모든 미리보기 .hwpx는 현재 작업 디렉터리의 output/ 에 저장 (SKILL.md 「결과 저장 위치」)
OUTPUT_DIR = Path("output")

sys.path.insert(0, str(SCRIPT_DIR))

from table_builder import (
    build_table_paragraph,
    is_preserve_design,
    list_templates,
    load_template,
    merge_template_styles_into_header,
)
from build_hwpx import build
from lxml import etree


# 템플릿별 샘플 데이터
SAMPLE_DATA = {
    "basic": {
        "data": [
            ["1", "교원연수", "AI 직무연수 운영 및 교원 역량 강화", "상반기"],
            ["2", "수업모델", "교과별 AI 활용 수업안 개발", "5개 교과"],
            ["3", "인프라 구축", "교내 AI 학습 플랫폼 도입 및 운영", "하반기"],
        ],
    },
    "status": {
        "data": [
            ["1", "시스템 구축", "클라우드 서버 이전 완료", "80%"],
            ["2", "교육 프로그램", "전직원 대상 교육 진행 중", "60%"],
            ["3", "보안 점검", "취약점 분석 및 패치 적용", "100%"],
        ],
    },
    "budget": {
        "data": [
            ["1", "인건비", "개발자 3명 인건비", "150,000", "-"],
            ["2", "장비 구매", "서버 및 네트워크 장비", "80,000", "입찰 예정"],
            ["3", "교육비", "직원 역량강화 교육", "20,000", "-"],
        ],
        "summary": ["", "", "합  계", "250,000", ""],
    },
    "schedule": {
        "data": [
            ["‘26.05.01", "검진기관 선정 및 계약 체결", "인사부"],
            ["‘26.05.10", "부서별 일정 배정 및 직원 개별 안내", "인사부"],
            ["‘26.06.01", "본사 및 지사 직원 건강검진", "검진기관"],
        ],
    },
    "checklist": {
        "data": [
            ["1", "신청서 및 첨부서류 구비 여부", "담당자", "완료", "-"],
            ["2", "배정 예산 범위 내 집행 여부", "재무팀", "완료", "-"],
            ["3", "결재권자 승인 완료 여부", "담당자", "완료", "-"],
        ],
    },
    "roadmap": {
        # preserve-design 표 — headers는 헤더 행 9개 셀(콘텐츠 5 + spacer 4) 순서,
        # data는 본문 행마다 콘텐츠 5칸 (sample 구조와 1:1)
        "headers": [
            "1단계", "", "2단계", "", "3단계", "", "4단계", "", "5단계",
        ],
        "data": [
            ["기획·설계", "공모·접수", "심사·평가", "본선·시상", "성과확산"],
            ["’26.4월", "’26.5월", "’26.6월", "’26.7월", "’26.8월"],
        ],
    },
}


def get_sample_data(template_name: str) -> dict:
    """템플릿에 맞는 샘플 데이터 반환. 없으면 기본 데이터 생성."""
    if template_name in SAMPLE_DATA:
        return SAMPLE_DATA[template_name]

    # 알 수 없는 템플릿: 3행 x 4열 기본 데이터
    return {
        "data": [
            ["1", "항목A", "내용A", "비고A"],
            ["2", "항목B", "내용B", "비고B"],
            ["3", "항목C", "내용C", "비고C"],
        ],
    }


def build_preview_section(template_name: str, id_mapping: dict | None = None) -> str:
    """표 템플릿을 포함한 section0.xml 문자열 생성."""
    sample = get_sample_data(template_name)

    table_para = build_table_paragraph(
        template=template_name,
        data=sample["data"],
        headers=sample.get("headers"),
        summary=sample.get("summary"),
        id_mapping=id_mapping,
        start_id=1000000050,
    )

    # base 템플릿의 secPr 가져오기
    base_section_path = SKILL_DIR / "templates" / "base" / "Contents" / "section0.xml"
    base_section = base_section_path.read_text(encoding="utf-8")

    # secPr이 포함된 첫 번째 <hp:p>...</hp:p> 추출
    first_p_end = base_section.index("</hp:p>") + len("</hp:p>")
    secpr_para = base_section[base_section.index("<hp:p"):first_p_end]

    section = f"""<?xml version='1.0' encoding='UTF-8'?>
<hs:sec xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app"
        xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"
        xmlns:hp10="http://www.hancom.co.kr/hwpml/2016/paragraph"
        xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
        xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"
        xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"
        xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history"
        xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page"
        xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf"
        xmlns:dc="http://purl.org/dc/elements/1.1/"
        xmlns:opf="http://www.idpf.org/2007/opf/"
        xmlns:ooxmlchart="http://www.hancom.co.kr/hwpml/2016/ooxmlchart"
        xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar"
        xmlns:epub="http://www.idpf.org/2007/ops"
        xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0">
  {secpr_para}
  <hp:p id="1000000048" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
    <hp:run charPrIDRef="0"><hp:t>{template_name} 표 템플릿 미리보기</hp:t></hp:run>
  </hp:p>
  <hp:p id="1000000049" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
    <hp:run charPrIDRef="0"><hp:t/></hp:run>
  </hp:p>
  {table_para}
  <hp:p id="1000000099" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">
    <hp:run charPrIDRef="0"><hp:t/></hp:run>
  </hp:p>
</hs:sec>
"""
    return section


def preview_single(template_name: str, output_path: Path) -> None:
    """단일 템플릿 미리보기 HWPX 생성."""
    import tempfile

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # preserve-design 표는 보고서 header.xml에 lib 스타일을 머지한
    # 패치 header를 사용해야 디자인이 깨지지 않는다.
    header_override = None
    id_mapping = None
    patched_header_path = None
    if is_preserve_design(load_template(template_name)):
        rep_header_path = SKILL_DIR / "templates" / "report" / "header.xml"
        rep_header = etree.parse(str(rep_header_path))
        id_mapping = merge_template_styles_into_header(template_name, rep_header)
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".xml", delete=False
        ) as f:
            rep_header.write(f, xml_declaration=True,
                             encoding="UTF-8", standalone=True)
            patched_header_path = Path(f.name)
        header_override = patched_header_path

    section_xml = build_preview_section(template_name, id_mapping=id_mapping)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".xml", delete=False, encoding="utf-8"
    ) as f:
        f.write(section_xml)
        section_path = Path(f.name)

    try:
        build(
            template="report",
            header_override=header_override,
            section_override=section_path,
            title=f"{template_name} 표 템플릿 미리보기",
            creator="preview_table.py",
            output=output_path,
        )
    finally:
        section_path.unlink(missing_ok=True)
        if patched_header_path is not None:
            patched_header_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="표 템플릿을 한글(HWPX) 미리보기 파일로 변환"
    )
    parser.add_argument(
        "template",
        nargs="?",
        help="미리보기할 표 템플릿 이름 (예: basic, budget, schedule)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="출력 .hwpx 파일 경로 (기본: output/{템플릿명}_preview.hwpx)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="모든 표 템플릿을 한 번에 미리보기 생성",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="사용 가능한 표 템플릿 목록 출력",
    )
    args = parser.parse_args()

    if args.list:
        templates = list_templates()
        print("사용 가능한 표 템플릿:")
        for name, desc in templates:
            print(f"  {name:12s}  {desc}")
        return

    if args.all:
        templates = list_templates()
        for name, desc in templates:
            output = OUTPUT_DIR / f"{name}_preview.hwpx"
            print(f"생성 중: {name} → {output.name}")
            try:
                preview_single(name, output)
            except Exception as e:
                print(f"  오류: {e}", file=sys.stderr)
        return

    if not args.template:
        parser.print_help()
        sys.exit(1)

    output = args.output or OUTPUT_DIR / f"{args.template}_preview.hwpx"
    preview_single(args.template, output)


if __name__ == "__main__":
    main()
