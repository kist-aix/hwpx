#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""style_check.py — 생성된 HWPX/섹션 XML의 개조식 문체 규칙 검사.

SKILL.md 「본문 문체 규칙」을 기계적으로 점검한다:
  - □ 상위 줄 : '□ ' 뒤 기준(공백·괄호·문장부호 포함) 30자 이상 35자 이내
      · 단, '라벨 : 값' 형식의 라벨형 줄은 30자 하한 예외 (35자 상한은 적용)
  - ❍ 하위 줄 : '❍ ' 뒤 기준 65자 이상 70자 이내
  - □/❍ 줄 종결 : 합니다·습니다·한다·된다·있다·큼·함 으로 끝나면 위반

검사 대상은 hs:sec 직속 본문 문단(□/❍)이며, 표 셀 텍스트는 제외한다.

Usage:
    python style_check.py output/report.hwpx
    python style_check.py section0.xml

종료코드: 0 통과 / 1 위반 / 2 사용오류
"""
import sys
import zipfile
from pathlib import Path

from lxml import etree

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HP_P = f"{{{HP}}}p"
HP_RUN = f"{{{HP}}}run"
HP_T = f"{{{HP}}}t"

DOMARK = "□"
OMARK = "❍"
BAD_ENDINGS = ("합니다", "습니다", "한다", "된다", "있다", "큼", "함")
DO_MIN, DO_MAX = 30, 35   # □ 줄 글자 수 범위
O_MIN, O_MAX = 65, 70     # ❍ 줄 글자 수 범위
LABEL_MAX = 10            # 라벨형 판정: ' : ' 앞 라벨 최대 길이


def load_section(path: Path):
    """HWPX(zip)면 Contents/section0.xml을, 아니면 파일 자체를 파싱."""
    if zipfile.is_zipfile(str(path)):
        with zipfile.ZipFile(str(path)) as zf:
            return etree.fromstring(zf.read("Contents/section0.xml"))
    return etree.fromstring(path.read_bytes())


def para_own_text(p) -> str:
    """문단 자신의 텍스트만 이어 붙임 (중첩 표 셀 텍스트는 제외)."""
    parts = []
    for run in p.findall(HP_RUN):
        for t in run.findall(HP_T):
            if t.text:
                parts.append(t.text)
    return "".join(parts).strip()


def is_label_line(content: str) -> bool:
    """'라벨 : 값' 형식의 라벨형 줄인지 — □ 30자 하한 예외 대상."""
    idx = content.find(" : ")
    if idx <= 0:
        return False
    return len(content[:idx].strip()) <= LABEL_MAX


def _ending_violation(content: str):
    """피해야 할 종결로 끝나면 해당 종결 문자열을, 아니면 None."""
    tail = content.rstrip(" .·")
    for b in BAD_ENDINGS:
        if tail.endswith(b):
            return b
    return None


def check(path: Path):
    """(종류, 내용, 글자수, [위반사유], 라벨형여부) 목록 반환."""
    root = load_section(path)
    results = []
    for p in root.findall(HP_P):          # hs:sec 직속 본문 문단만
        text = para_own_text(p)
        if text.startswith(DOMARK):
            content = text[1:].lstrip()
            n = len(content)
            label = is_label_line(content)
            v = []
            if n > DO_MAX:
                v.append(f"길이 {n}자 — {DO_MAX}자 초과")
            elif n < DO_MIN and not label:
                v.append(f"길이 {n}자 — {DO_MIN}자 미만")
            bad = _ending_violation(content)
            if bad:
                v.append(f"종결 '~{bad}'")
            results.append(("□", content, n, v, label))
        elif text.startswith(OMARK):
            content = text[1:].lstrip()
            n = len(content)
            v = []
            if n > O_MAX:
                v.append(f"길이 {n}자 — {O_MAX}자 초과")
            elif n < O_MIN:
                v.append(f"길이 {n}자 — {O_MIN}자 미만")
            bad = _ending_violation(content)
            if bad:
                v.append(f"종결 '~{bad}'")
            results.append(("❍", content, n, v, False))
    return results


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python style_check.py <file.hwpx | section0.xml>",
              file=sys.stderr)
        sys.exit(2)
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"오류: 파일을 찾을 수 없음: {path}", file=sys.stderr)
        sys.exit(2)

    results = check(path)
    print(f"문체 검사: {path}")
    if not results:
        print("  □/❍ 본문 줄을 찾지 못했습니다.")
        sys.exit(0)

    violations = 0
    for kind, content, n, v, label in results:
        if v:
            violations += 1
            preview = content[:32] + ("…" if len(content) > 32 else "")
            print(f"  X [{kind} {n:3d}자] {' / '.join(v)}")
            print(f"      {preview}")

    do_n = sum(1 for r in results if r[0] == "□")
    o_n = len(results) - do_n
    label_n = sum(1 for r in results if r[4])
    print(f"  검사 {len(results)}줄 (□ {do_n} / ❍ {o_n}) — "
          f"라벨형 {label_n}줄 하한 예외 — 위반 {violations}건")
    if violations:
        print("INVALID: 문체 규칙 위반")
        sys.exit(1)
    print("VALID: 문체 규칙 통과")
    sys.exit(0)


if __name__ == "__main__":
    main()
