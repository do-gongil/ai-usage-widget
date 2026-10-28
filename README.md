# AI Usage Widget

Claude Code / Codex CLI의 **5시간·주간 한도 사용률**을 Windows 트레이 아이콘과 항상 위에 떠 있는 작은 창(PiP)으로 표시합니다. (Windows 10/11 전용, 비공식 도구)

> **[Microsoft Store](https://apps.microsoft.com/detail/9NN9GN3KMSWN)에 배포되는 C#/WinUI 3 앱(v1.0.9, `UsageWidget/`)입니다.** 이전 Python 버전은 [`python-legacy`](https://github.com/do-gongil/ai-usage-widget/tree/python-legacy) 태그에 남아 있습니다(더 이상 관리하지 않음).

| PiP 창 | 미니 모드 |
|---|---|
| ![PiP 창](docs/widget.png) | ![미니 모드](docs/widget-mini.png) |

## 기능

**트레이 아이콘**
- 숫자: Claude 사용률 (Claude를 끄면 Codex). 좌측 상단 뱃지 `5`(5시간) / `W`(주간)
- 색: 초록 < 60% · 주황 60–79% · 빨강 ≥ 80% · 한도 소진 `!` · 회색 = 조회 실패(직전 값 표시, 없으면 `?`)
- 마우스 오버: 5시간/주간 %, 리셋 시각, 마지막 갱신 시각
- 좌클릭: PiP 보이기/숨기기
- 우클릭: Claude / Codex 선택, Claude Code 즉시 반영, PiP 보기, 아이콘 5시간·주간 전환, 지금 새로고침, 시작 시 실행, 종료

**PiP 창**
- 5시간·주간 사용률 막대와 리셋 시각. 빈 곳을 끌어 옮기고, 오른쪽 아래 `◢`로 크기를 조절합니다.
- 상단: ⟳ 새로고침 · 갱신 시각 · ⚙ 설정(항상 위, 창 색상, 투명도 30–100%) · — 미니 모드 · ✕ 숨기기(종료는 트레이에서)
- **미니 모드**: 상단 행 없이 작업 표시줄 높이(48px)의 막대만. `—` 버튼 또는 전역 단축키 **Ctrl+Alt+U**로 전환, 오른쪽 ↗ 버튼으로 복귀. 일반/미니 창의 위치·크기는 따로 기억합니다.
- 테두리 없는 위젯 창이라 작업 표시줄에는 나타나지 않습니다.

**공통**
- 한 번에 하나만 실행됩니다. 5분마다 갱신하고, 요청 제한(429)을 받으면 최대 10분까지 조회 간격을 늘립니다. 조회에 성공한 뒤 5분 안에는 새로고침을 눌러도 Claude를 다시 조회하지 않습니다(429 예방).
- 설정: `%APPDATA%\UsageTray\config.json` (`interval` 300~86400초)
- **Claude Code 즉시 반영**(트레이 메뉴): Claude Code의 `statusLine`에 연결해, Claude Code를 쓰는 동안 응답마다 사용률을 바로 반영합니다(API 조회 없음). 기존 statusLine 명령(claude-hud 등)은 그대로 이어서 실행되고, 끄면 원래 설정으로 되돌립니다. `settings.json`을 바꿀 때마다 `settings.json.usagewidget.bak`으로 백업합니다.

## 설치

**[Microsoft Store에서 받기](https://apps.microsoft.com/detail/9NN9GN3KMSWN)** — 설치·업데이트·제거 모두 Store에서 처리됩니다.

- **Claude Code에 로그인되어 있어야 합니다**(`claude` 실행 → 로그인). 웹·데스크톱 앱만 쓰는 경우에도 Claude Code로 한 번 로그인하면 같은 계정의 사용률이 표시됩니다.

## 아이콘을 항상 보이게 하기

새 트레이 아이콘은 기본적으로 `^` 숨김 영역에 들어갑니다.
설정 → 개인 설정 → 작업 표시줄 → **기타 시스템 트레이 아이콘**에서 Session Usage Widget을 켜 주세요.

## 동작 방식과 보안

| 대상 | 방식 |
|---|---|
| Claude | `%USERPROFILE%\.claude\.credentials.json`의 OAuth 토큰으로 `https://api.anthropic.com/api/oauth/usage`를 조회. 즉시 반영을 켜면 Claude Code가 statusLine에 넘기는 `rate_limits`를 `%APPDATA%\UsageTray\claude-live.json`으로 받아 먼저 사용 |
| Codex | `%CODEX_HOME%` 또는 `%USERPROFILE%\.codex\sessions`의 최신 jsonl에서 `rate_limits`를 읽음 (네트워크 안 씀) |

- **사용자 본인의 PC 로그인 정보**를 사용합니다. 저장소에는 어떤 인증 정보도 들어 있지 않습니다.
- 토큰은 **읽기만** 하며 저장하거나 기록하지 않고, `api.anthropic.com` 외의 곳으로 보내지 않습니다(리다이렉트도 따라가지 않음). 토큰 갱신은 Claude Code에 맡깁니다.
- 사용률 조회는 모델을 호출하지 않으므로 사용량을 소모하지 않습니다.

## 한계

- `/api/oauth/usage`는 **공식 문서에 없는 엔드포인트**라 예고 없이 바뀔 수 있습니다.
- 토큰이 만료되면 "토큰 만료"로 표시됩니다. Claude Code를 한 번 실행하면 다시 정상으로 돌아옵니다.
- Codex 값은 **Codex를 마지막으로 사용한 시점** 기준입니다.
- API 키(Console 과금) 사용자에게는 5시간·주간 한도가 없어 표시할 값이 없습니다.
- 이 도구는 Anthropic·OpenAI와 무관한 비공식 도구입니다.

## 구조

```
UsageWidget/          C#/WinUI 3 앱 (Store 버전, MSIX)
UsageWidget.Tests/    C# 단위 테스트
build_store.bat       Store용 MSIX 빌드
tools/make_icon.py    앱 아이콘·MSIX 로고 생성 (Python + Pillow)
```

## 테스트

```
dotnet test UsageWidget.Tests
```
