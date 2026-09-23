# Usage Tray

Claude Code / Codex CLI의 **5시간·주간 한도 사용률**을 Windows 작업 표시줄 트레이에 표시합니다. (Windows 10/11 전용, 비공식 도구)

- 아이콘 숫자: Claude 사용률 (Claude를 끄면 Codex)
- **좌클릭: 5시간 ↔ 주간 전환** — 현재 보기는 우클릭 메뉴 항목 이름으로 확인, 선택은 저장됨
- 색: 초록 < 60% · 주황 60–79% · 빨강 ≥ 80% · 한도 소진 `!` · 회색 = 조회 실패(직전 값 표시, 없으면 `?`)
- 한 번에 하나만 실행됩니다. 요청 제한(429)을 받으면 최대 10분까지 조회 간격을 늘립니다.
- 마우스 오버: 5시간/주간 %, 리셋 시각, 마지막 갱신 시각
- 우클릭: Claude / Codex 사용 선택, 5시간·주간 보기, 지금 새로고침, 시작 시 실행, 종료
- 60초마다 갱신 (`%APPDATA%\UsageTray\config.json`의 `interval`, 최소 30)

## 설치

**exe**: [Releases](../../releases)에서 `UsageTray.exe`를 받아 실행합니다. 코드 서명이 없어서 SmartScreen 경고가 뜨면 "추가 정보 → 실행"을 누르세요.

**소스**:
```
pip install -r requirements.txt
pythonw usage_tray.pyw
```

직접 빌드하려면 `build.bat`을 실행하세요. `dist\UsageTray.exe`가 만들어집니다.

## 아이콘을 항상 보이게 하기

새 트레이 아이콘은 기본적으로 `^` 숨김 영역에 들어갑니다.
설정 → 개인 설정 → 작업 표시줄 → **기타 시스템 트레이 아이콘**에서 UsageTray를 켜 주세요.

## 동작 방식과 보안

| 대상 | 방식 |
|---|---|
| Claude | `%USERPROFILE%\.claude\.credentials.json`의 OAuth 토큰으로 `https://api.anthropic.com/api/oauth/usage`를 조회 |
| Codex | `%CODEX_HOME%` 또는 `%USERPROFILE%\.codex\sessions`의 최신 jsonl에서 `rate_limits`를 읽음 (네트워크 안 씀) |

- **사용자 본인의 PC 로그인 정보**를 사용합니다. 저장소에는 어떤 인증 정보도 들어 있지 않습니다.
- 토큰은 **읽기만** 하며 저장하거나 기록하지 않고, `api.anthropic.com` 외의 곳으로 보내지 않습니다. 토큰 갱신은 Claude Code에 맡깁니다.
- 사용률 조회는 모델을 호출하지 않으므로 사용량을 소모하지 않습니다.

## 한계

- `/api/oauth/usage`는 **공식 문서에 없는 엔드포인트**라 예고 없이 바뀔 수 있습니다.
- 토큰이 만료되면 "토큰 만료"로 표시됩니다. Claude Code를 한 번 실행하면 다시 정상으로 돌아옵니다.
- Codex 값은 **Codex를 마지막으로 사용한 시점** 기준입니다. Codex 표시는 아직 실사용 데이터로 충분히 검증되지 않았으니, 값이 이상하면 이슈로 알려주세요.
- API 키(Console 과금) 사용자에게는 5시간·주간 한도가 없어 표시할 값이 없습니다.
- 이 도구는 Anthropic·OpenAI와 무관한 비공식 도구입니다.

## 테스트

```
python test_usage_tray.py
```
