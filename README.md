# hwpx — 한글파일(.hwpx) 보고서 자동 생성 스킬 for Claude Code

**한글 보고서를 Claude에게 맡기는 스킬입니다.**
"어떤 내용으로 어떤 보고서를 만들어줘"라고 알려주면, 공공기관 보고서 양식(머리말·제목·항목·표)에 맞춰 정돈된 한글파일(.hwpx)을 자동으로 만들어 줍니다. 사용자는 작성할 내용에만 집중하면 됩니다.

## 주요 기능

- **정돈된 보고서 양식**: 머리말·제목 도형·소제목·□ 항목 등 공공기관 보고서 형식이 미리 짜여 있어, 내용만 알려주면 그 양식에 맞춰 한글 문서가 만들어집니다.
- **표를 손쉽게 삽입**: 일반표·현황표·예산표·일정표·점검표 5종 양식이 준비되어 있어, 들어갈 데이터만 알려주면 표가 자동으로 그려집니다.
- **표 양식 맞춤 제작**: 기본 5종 외에, 표를 한글에서 원하는 형태로 디자인해 스킬의 표 템플릿으로 바로 반영할 수 있습니다.
- **개조식 문체 규칙**: 공공기관 보고서 문체(□ 상위 줄·❍ 하위 줄 길이, 명사형 종결)를 규칙으로 정의하고, 생성 결과를 자동 점검합니다.
- **기존 문서 활용**: 이미 가지고 있는 한글파일에서 텍스트만 뽑아내거나, 일부 내용을 수정하는 도구도 함께 들어있습니다.

> 한글파일을 첨부해도 그 양식을 똑같이 재현하지는 않습니다. 첨부 파일의 내용은 참고하지만, 결과는 항상 이 스킬의 기본 보고서 양식으로 만들어집니다. 원본 양식 그대로 쓰고 싶으면 한글 오피스에서 직접 수정해주세요.

## 설치

> Claude Code 등 agent에게 GitHub URL(`https://github.com/kist-aix/hwpx`)만 주고 "이거 설치해줘"라고 부탁하면, agent가 아래 절차를 따라 설치합니다. 사용자가 직접 실행해도 동일합니다.

### 사용자 전역 스킬로 설치 (모든 프로젝트에서 사용 — 권장)

```bash
git clone --depth 1 https://github.com/kist-aix/hwpx.git ~/.claude/skills/hwpx
python3 -m pip install --user -r ~/.claude/skills/hwpx/requirements.txt
```

### 현재 프로젝트 전용 스킬로 설치

```bash
git clone --depth 1 https://github.com/kist-aix/hwpx.git .claude/skills/hwpx
python3 -m pip install --user -r .claude/skills/hwpx/requirements.txt
```

설치 후 Claude Code를 재시작하면 "한글파일 생성", "보고서 만들어줘", ".hwpx 작성" 같은 요청 시 자동으로 스킬이 호출됩니다.

### 업데이트

```bash
# 사용자 전역
git -C ~/.claude/skills/hwpx pull

# 프로젝트 전용
git -C .claude/skills/hwpx pull
```

### 제거

```bash
rm -rf ~/.claude/skills/hwpx        # 사용자 전역
rm -rf .claude/skills/hwpx          # 프로젝트 전용
```

## 의존성

**별도 설치 작업 불필요.** 스킬이 처음 호출될 때 필요한 Python 패키지를 자동으로 확인·설치합니다(약 10~30초). 비개발자 사용자도 추가 명령을 입력할 필요가 없습니다.

내부적으로 사용되는 패키지(참고용):

- `lxml` (필수, 자동 설치)
- `python-hwpx` (텍스트 추출 기능을 쓸 때만 사용, 함께 자동 설치)

오프라인 환경 등 자동 설치가 불가능한 경우에만 미리 수동 설치:

```bash
pip install --user -r requirements.txt
```

## 디렉토리 구조

```
hwpx/                            # 이 리포지토리 = 스킬 본체
├── SKILL.md                     # 스킬 본문 (자세한 사용법)
├── requirements.txt
├── scripts/                     # build_hwpx·table_builder·preview_table·extract_table_templates·style_check·validate·text_extract
├── templates/                   # report/ (보고서 양식), tables/ (표 템플릿), base/ (내부 스켈레톤)
├── assets/                      # 표 라이브러리·시각 기준 .hwpx
├── references/                  # OWPML 포맷 참조 문서
├── README.md
└── LICENSE
```

자세한 사용법, XML 작성 가이드, 스타일 ID 맵은 [`SKILL.md`](SKILL.md)를 참조하세요.

## 변경 이력

### v0.4 — 표 디자인 보존 모드 (2026-07-01)

- **표 디자인 보존 모드 추가** — 라벨 끝에 `[design]` 마커를 붙인 표는 정규화를 건너뛰고 셀별 테두리·색·글꼴을 원본 그대로 보존. 마일스톤·로드맵처럼 셀마다 다르게 디자인한 시각화 표가 평준화되지 않음. 추출 시 표가 참조하는 스타일 정의를 `meta/extra-styles`에 함께 담고, 빌드 시 보고서 헤더에 새 ID로 머지하여 삽입
- **로드맵 표 템플릿 추가** — `templates/tables/roadmap.xml`: 5단계 일자별 진행일정 로드맵 표
- **문체 규칙 명문화** — ❍ 줄 들여쓰기(공백 2칸)와 양식 빈 줄(제목 도형 직후·섹션 구분) 규칙을 `SKILL.md`에 추가

### v0.3 — 표 셀 여백 보존·표 라이브러리 디자인 갱신 (2026-05-21)

- **표 셀 여백 보존** — `extract_table_templates.py`가 셀의 문단 여백(`paraPr` 좌우 margin)을 `cellMargin`으로 흡수. 한글에서 '문단 여백'으로 준 표 여백도 추출·재추출에서 깨지지 않고 유지
- **표 라이브러리 디자인 갱신** — `all_tables_preview.hwpx`의 표 너비·열폭·셀 여백을 조정하고 표 템플릿 5종을 재추출

### v0.2 — 표 양식 추출·문체 검사 도입 (2026-05-21)

- **표 양식 추출 기능 추가** — `extract_table_templates.py`: 한글파일(표 라이브러리)에 디자인한 표를 `templates/tables/*.xml` 표 템플릿으로 자동 변환. 모든 스타일 ID를 보고서 표준 표 서식으로 정규화하여, 어떤 한글파일에서 추출해도 글꼴·테두리가 깨지지 않음
- **문체 검사기 추가** — `style_check.py`: 생성된 `.hwpx`가 개조식 문체 규칙(□ 30~35자, ❍ 65~70자, 명사형 종결)을 지키는지 자동 점검
- **본문 문체 규칙 명문화** — 개조식 작성 지침(□/❍ 줄 길이·종결, 라벨형 줄 30자 하한 예외)을 `SKILL.md`에 추가
- **표 날짜 형식 규칙** — 표의 일자 열은 `‘YY.MM.DD` 형식으로 통일
- **미리보기 출력 경로 정리** — `preview_table.py`가 미리보기 `.hwpx`를 `output/`에 생성하도록 변경 (스킬 루트 오염 방지)
- **표 정합성 정리** — `schedule`·`checklist` 표의 설명·샘플 데이터를 실제 열 구성에 맞게 수정
- `.gitignore` 추가

### v0.1 — 최초 릴리스 (2026-05-18)

- hwpx 스킬 최초 공개 — 공공기관 보고서 양식 기반 한글파일(.hwpx) 자동 생성
- 보고서 빌드(`build_hwpx.py`), 표 템플릿 5종, 미리보기·검증·텍스트 추출 도구 제공

## 라이선스

[MIT](LICENSE)
