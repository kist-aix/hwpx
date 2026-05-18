# hwpx — 한글파일(.hwpx) 보고서 자동 생성 스킬 for Claude Code

**한글 보고서를 Claude에게 맡기는 스킬입니다.**
"어떤 내용으로 어떤 보고서를 만들어줘"라고 알려주면, 공공기관 보고서 양식(머리말·제목·항목·표)에 맞춰 정돈된 한글파일(.hwpx)을 자동으로 만들어 줍니다. 사용자는 작성할 내용에만 집중하면 됩니다.

## 주요 기능

- **정돈된 보고서 양식**: 머리말·제목 도형·소제목·□ 항목 등 공공기관 보고서 형식이 미리 짜여 있어, 내용만 알려주면 그 양식에 맞춰 한글 문서가 만들어집니다.
- **표를 손쉽게 삽입**: 일반표·현황표·예산표·일정표·점검표 5종 양식이 준비되어 있어, 들어갈 데이터만 알려주면 표가 자동으로 그려집니다.
- **기존 문서 활용**: 이미 가지고 있는 한글파일에서 텍스트만 뽑아내거나, 일부 내용을 수정하는 도구도 함께 들어있습니다.

> 한글파일을 첨부해도 그 양식을 똑같이 재현하지는 않습니다. 첨부 파일의 내용은 참고하지만, 결과는 항상 이 스킬의 기본 보고서 양식으로 만들어집니다. 원본 양식 그대로 쓰고 싶으면 한글 오피스에서 직접 수정해주세요.

## 설치

> Claude Code 등 agent에게 GitHub URL(`https://github.com/mskim8717/hwpx`)만 주고 "이거 설치해줘"라고 부탁하면, agent가 아래 절차를 따라 설치합니다. 사용자가 직접 실행해도 동일합니다.

### 사용자 전역 스킬로 설치 (모든 프로젝트에서 사용 — 권장)

```bash
git clone --depth 1 https://github.com/mskim8717/hwpx.git ~/.claude/skills/hwpx
python3 -m pip install --user -r ~/.claude/skills/hwpx/requirements.txt
```

### 현재 프로젝트 전용 스킬로 설치

```bash
git clone --depth 1 https://github.com/mskim8717/hwpx.git .claude/skills/hwpx
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
├── scripts/                     # build_hwpx, table_builder, validate, text_extract 등
├── templates/                   # report/ (보고서 양식), tables/ (표 템플릿), base/ (내부 스켈레톤)
├── assets/                      # 시각 기준 .hwpx 샘플
├── references/                  # OWPML 포맷 참조 문서
├── README.md
└── LICENSE
```

자세한 사용법, XML 작성 가이드, 스타일 ID 맵은 [`SKILL.md`](SKILL.md)를 참조하세요.

## 라이선스

[MIT](LICENSE)
