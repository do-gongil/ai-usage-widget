# Microsoft Store 제출 자료

Partner Center 제출 화면에 그대로 붙여 넣는 값들입니다.

## 0. 제출 전에 바꿀 값 (Partner Center > 제품 > 제품 관리 > 제품 ID)

`UsageWidget/Package.appxmanifest`:
- `Identity Name` ← "Package/Identity/Name"
- `Identity Publisher` ← "Package/Identity/Publisher" (`CN=...`)
- `PublisherDisplayName` ← "Package/Properties/PublisherDisplayName"

바꾼 뒤 `build_store.bat`을 실행하면 `dist\store\...\UsageWidget_<버전>_x64.msix`가 생깁니다. 이 파일을 "패키지"에 업로드합니다.

## 1. 앱 이름

Session Usage Widget

> "Claude", "Codex"는 상표라서 앱 이름에는 넣지 않고, 설명에만 호환 대상으로 적습니다.

## 2. 설명 (ko-KR 목록에 영어로 입력)

A small always-on-top widget and tray icon that shows your Claude Code and Codex usage (5-hour and weekly limits).

- 5-hour / weekly usage and time until reset
- Always-on-top PiP window and a taskbar-height mini mode (Ctrl+Alt+U)
- Window color and opacity settings, launch at Windows startup
- Everything runs on your PC; no data is sent to the developer

This is an unofficial app and is not affiliated with Anthropic or OpenAI. You need to be signed in to Claude Code or the Codex CLI.

## 3. 짧은 설명

Unofficial widget to check your Claude Code / Codex usage at a glance

## 4. 키워드 (최대 7개, "Claude Code"·"Codex"는 거부됨)

usage, widget, rate limit, tray, AI usage, token monitor, Always-on-top widget

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
