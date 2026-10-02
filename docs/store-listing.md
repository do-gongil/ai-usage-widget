# Microsoft Store 제출 자료

Partner Center 제출 화면에 그대로 붙여 넣는 값들입니다.

## 0. 제출 전에 바꿀 값 (Partner Center > 제품 > 제품 관리 > 제품 ID)

`UsageWidget/Package.appxmanifest`:
- `Identity Name` ← "Package/Identity/Name"
- `Identity Publisher` ← "Package/Identity/Publisher" (`CN=...`)
- `PublisherDisplayName` ← "Package/Properties/PublisherDisplayName"

바꾼 뒤 `build_store.bat`을 실행하면 `dist\store\...\UsageWidget_<버전>_x64.msix`가 생깁니다. 이 파일을 "패키지"에 업로드합니다.

## 1. 앱 이름

AI Usage Widget

> "Claude", "Codex"는 상표라서 앱 이름에는 넣지 않고, 설명에만 호환 대상으로 적습니다.

## 2. 설명 (ko-KR)

Claude Code와 Codex의 사용량(5시간·주간 한도)을 작은 항상 위 창과 트레이 아이콘으로 보여 주는 위젯입니다.

- 5시간 / 주간 사용률과 초기화까지 남은 시간 표시
- 항상 위 PiP 창, 작업 표시줄 높이의 미니 모드 (Ctrl+Alt+U)
- 창 색상·투명도 설정, Windows 시작 시 실행
- 모든 처리는 PC 안에서 이뤄지며 개발자에게 데이터를 보내지 않습니다

이 앱은 Anthropic 또는 OpenAI와 관련이 없는 비공식 앱입니다. Claude Code 또는 Codex CLI에 로그인되어 있어야 합니다.

## 3. 짧은 설명

Claude Code / Codex 사용량을 바로 확인하는 비공식 위젯

## 4. 키워드 (최대 7개)

usage, widget, Claude Code, Codex, rate limit, tray, 사용량

## 5. 기타 항목

- 범주: 개발자 도구
- 개인정보처리방침 URL: https://github.com/do-gongil/ai-usage-widget/blob/main/docs/privacy.md
  (이 파일이 main 브랜치에 있어야 링크가 열립니다)
- 지원 연락처: https://github.com/do-gongil/ai-usage-widget/issues
- 가격: 무료 / 시장: 전체
- 연령 등급 설문: 사용자 간 소통·구매·위치·개인정보 공유 모두 "아니요"
- 스크린샷: 최소 1장, 1366×768 이상. `docs/widget.png`는 위젯만 잘라 낸 작은 이미지라 전체 화면 캡처를 새로 찍어야 합니다.

## 6. 제한된 기능(runFullTrust) 사유 — "인증 참고 사항"에 입력

This is a desktop (Win32, WinUI 3) app packaged as MSIX. runFullTrust is required because the app reads
the user's local Claude Code credentials file (%USERPROFILE%\.claude\.credentials.json) and Codex session
logs (%USERPROFILE%\.codex\sessions) to display usage, and shows a system tray icon. No data is sent
anywhere except Anthropic's usage endpoint (api.anthropic.com).

## 7. 심사자용 테스트 안내 — "인증 참고 사항"에 함께 입력

The app needs a signed-in Claude Code or Codex CLI on the PC to show numbers. Without it, the widget
starts normally and shows "미로그인" (not signed in) / "기록 없음" (no records); the tray icon menu
(right-click) and the Ctrl+Alt+U mini-mode toggle can still be tested.
