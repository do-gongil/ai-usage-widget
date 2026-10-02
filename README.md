# Usage Widget

Claude Code / Codex CLI의 **5시간·주간 한도 사용률**을 Windows 트레이 아이콘과 항상 위에 떠 있는 작은 창(PiP)으로 표시합니다. (Windows 10/11 전용, 비공식 도구, C# / WinUI 3)

| PiP 창 | 미니 모드 |
|---|---|
| ![PiP 창](docs/widget.png) | ![미니 모드](docs/widget-mini.png) |

## 기능

**트레이 아이콘**
- 숫자: Claude 사용률 (Claude를 끄면 Codex). 좌측 상단 뱃지 `5`(5시간) / `W`(주간)
- 색: 초록 < 60% · 주황 60–79% · 빨강 ≥ 80% · 한도 소진 `!` · 회색 = 조회 실패(직전 값 표시, 없으면 `?`)
- 마우스 오버: 5시간/주간 %, 리셋 시각, 마지막 갱신 시각
- 좌클릭: PiP 보이기/숨기기
- 우클릭: Claude / Codex 선택, PiP 보기, 아이콘 5시간·주간 전환, 지금 새로고침, 시작 시 실행, 종료

**PiP 창**
- 5시간·주간 사용률 막대와 리셋 시각. 크기 조절 가능, X는 숨기기(종료는 트레이에서)
- 상단: ↻ 새로고침 · 갱신 시각 · ⚙ 설정(항상 위, 창 색상, 투명도 30–100%) · (빈 곳을 잡고 창 이동) · — 미니 모드 · ✕
- **미니 모드**: 상단 행 없이 작업 표시줄 높이(48px)의 막대만. `—` 버튼 또는 전역 단축키 **Ctrl+Alt+U**로 전환, 오른쪽 ↗ 버튼으로 복귀. 일반/미니 창의 위치·크기는 따로 기억

**공통**
- 한 번에 하나만 실행됩니다. 5분마다 갱신하고, 요청 제한(429)을 받으면 최대 10분까지 조회 간격을 늘립니다.
- 설정: `%APPDATA%\UsageTray\config.json` (`interval` 최소 300초 — 더 짧으면 429)

## 설치

**설치 파일 (추천)**
1. [Releases](https://github.com/do-gongil/ai-usage-widget/releases/latest)에서 `ai-usage-widget-setup.exe`를 받아 실행합니다. 관리자 권한은 필요 없고, `%LOCALAPPDATA%\Programs\ai-usage-widget`에 설치되며 시작 메뉴에 등록됩니다.
2. 트레이 아이콘을 우클릭해 **시작 시 실행**을 켜 두면 로그인할 때 자동으로 뜹니다.
3. 업데이트는 새 설치 파일을 실행하면 되고, 제거는 Windows 설정 → 앱에서 "AI Usage Widget"을 제거합니다(설정 `%APPDATA%\UsageTray`는 남습니다).

**zip (설치 없이)**
1. Releases에서 `ai-usage-widget-win-x64.zip`을 받아 원하는 위치에 압축을 풉니다.
2. `UsageWidget\UsageWidget.exe`를 실행합니다. .NET 설치는 필요 없습니다.

- **Claude Code에 로그인되어 있어야 합니다**(`claude` 실행 → 로그인). 웹·데스크톱 앱만 쓰는 경우에도 Claude Code로 한 번 로그인하면 같은 계정의 사용률이 표시됩니다.
- 코드 서명이 없어서 처음 실행할 때 SmartScreen 경고가 뜰 수 있습니다. **추가 정보 → 실행**을 누르세요.
- Windows의 **Smart App Control**이 켜진 PC에서는 서명 없는 앱이 차단되어 실행되지 않습니다(실행 직후 아무 반응 없이 종료). 이 경우 소스에서 직접 빌드해 보세요(아래).
- zip 업데이트: 앱을 트레이에서 종료한 뒤 새 zip의 내용으로 폴더를 덮어씁니다. 설정은 `%APPDATA%\UsageTray`에 있어 유지됩니다.
- zip 제거: 트레이에서 "시작 시 실행"을 끄고 종료한 뒤 폴더와 `%APPDATA%\UsageTray`를 삭제합니다.

## 빌드와 실행

[.NET 8 SDK](https://aka.ms/dotnet/download)가 필요합니다.

```
git clone https://github.com/do-gongil/ai-usage-widget.git
cd ai-usage-widget
build_widget.bat
```
테스트가 통과하면 `dist\release\UsageWidget\UsageWidget.exe`(.NET 런타임 포함 자체 포함 폴더, 약 160MB)와 배포용 `dist\ai-usage-widget-win-x64.zip`이 만들어집니다.

개발 중에는 Debug 빌드로 실행합니다.
```
cd UsageWidget
dotnet build -c Debug -p:Platform=x64
bin\x64\Debug\net8.0-windows10.0.19041.0\win-x64\UsageWidget.exe
```
앱이 켜져 있으면 exe가 잠겨 빌드가 실패하니 트레이 메뉴에서 먼저 종료하세요.

### Smart App Control

Windows의 Smart App Control이 켜져 있으면 서명 없는 빌드가 차단될 수 있습니다(실행 직후 종료, 이벤트 로그에 `애플리케이션 제어 정책에서 이 파일을 차단했습니다`).
빌드마다 판단이 달라서 `dotnet build --no-incremental`로 다시 빌드하면 통과하기도 하지만, 확실한 방법은 코드 서명(Azure Trusted Signing 등)이나 Microsoft Store(MSIX) 배포입니다.

## Python 버전 (Smart App Control이 켜진 PC용)

`python/`은 같은 기능(트레이 아이콘, PiP 창, 설정 팔레트, 미니 모드·Ctrl+Alt+U, 429 예방)을 Python으로 만든 버전입니다.
서명된 `pythonw.exe`가 스크립트를 실행하므로 **Smart App Control이 켜져 있어도 차단되지 않습니다.** 설정 파일과 단일 실행 뮤텍스를 C# 버전과 공유하므로 둘 중 하나만 실행됩니다.

```
cd python
pip install -r requirements.txt
pythonw usage_widget.pyw
```

- 트레이 아이콘 좌클릭: PiP 보이기/숨기기. 트레이 우클릭 메뉴의 "시작 시 실행"은 `pythonw usage_widget.pyw`를 자동 실행 항목으로 등록합니다.
- PiP 창은 테두리 없는 위젯 창이라 작업 표시줄에 나타나지 않습니다. 빈 곳을 끌어 옮기고, 오른쪽 아래 `◢`로 크기를 조절합니다.
- 테스트: `python test_usage_core.py` (또는 `pytest`)

## 아이콘을 항상 보이게 하기

새 트레이 아이콘은 기본적으로 `^` 숨김 영역에 들어갑니다.
설정 → 개인 설정 → 작업 표시줄 → **기타 시스템 트레이 아이콘**에서 UsageWidget을 켜 주세요.

## 동작 방식과 보안

| 대상 | 방식 |
|---|---|
| Claude | `%USERPROFILE%\.claude\.credentials.json`의 OAuth 토큰으로 `https://api.anthropic.com/api/oauth/usage`를 조회 |
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
UsageWidget/          WinUI 3 앱
  App.xaml.cs           트레이 아이콘·메뉴, 조회 루프, 아이콘 렌더링
  MainWindow.xaml(.cs)  PiP 창, 설정 팔레트, 미니 모드
  UsageService.cs       조회·파싱 로직 (UI 의존 없음)
  Settings.cs           config.json / last.json
UsageWidget.Tests/    UsageService·Settings 단위 테스트 (xUnit)
build_widget.bat      테스트 → 릴리스 빌드 → zip → 설치 파일
installer.iss         Inno Setup 설치 스크립트
python/               Python 버전
  usage_widget.pyw      트레이(pystray) + PiP 창(tkinter)
  usage_core.py         조회·파싱·설정 (UI 없음)
  test_usage_core.py    단위 테스트
```

## 테스트

```
dotnet test UsageWidget.Tests
python python/test_usage_core.py
```
