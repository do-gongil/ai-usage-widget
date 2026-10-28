# Session Usage Widget — 개인정보처리방침 / Privacy Policy

최종 수정: 2026-10-28

## 한국어

Session Usage Widget(이하 "앱")은 사용자의 PC에서만 동작하며, 개발자는 어떤 데이터도 수집하지 않습니다.

- **읽는 정보**
  - Claude Code 로그인 정보(`%USERPROFILE%\.claude\.credentials.json`)의 액세스 토큰: Claude 사용량을 조회하는 데만 씁니다.
  - Codex 세션 기록(`%USERPROFILE%\.codex\sessions`): 사용량 수치를 PC 안에서 읽기만 합니다.
- **Claude Code 즉시 반영(선택, 기본 꺼짐)**: 트레이 메뉴에서 켜면 Claude Code 설정(`%USERPROFILE%\.claude\settings.json`)의 `statusLine` 명령을 바꿉니다(바꾸기 전 파일은 `settings.json.usagewidget.bak`으로 백업, 끄면 원래 명령으로 복원). 이후 Claude Code가 사용량 수치를 `%USERPROFILE%\.claude\claude-live.json`에 쓰고 앱은 이를 읽기만 합니다. 이 파일은 PC 밖으로 보내지 않습니다.
- **네트워크 전송**: 위 토큰은 Anthropic의 사용량 조회 주소(`https://api.anthropic.com/api/oauth/usage`)에만 보냅니다. 그 밖의 서버(개발자 서버 포함)로는 아무것도 보내지 않습니다.
- **저장하는 정보**: 창 위치, 표시 설정, 마지막 사용량 수치를 PC 안의 앱 전용 폴더(`%LOCALAPPDATA%\Packages\do-gongil.SessionUsageWidget_<ID>\LocalCache\Roaming\UsageTray`)에만 저장합니다. 토큰은 저장하지 않습니다.
- **수집·분석·광고**: 사용 통계, 분석 도구, 광고, 제3자 공유가 모두 없습니다.
- **삭제**: 앱을 제거하면 위 폴더의 설정과 마지막 수치도 함께 삭제됩니다. Codex 파일과 Claude Code 로그인 정보는 건드리지 않습니다. 즉시 반영을 켰다면 제거 전에 트레이 메뉴에서 꺼야 `settings.json`이 원래대로 돌아가고, `claude-live.json`은 남으므로 필요하면 직접 지웁니다. 이전에 GitHub의 Python 버전을 쓴 적이 있다면 그 버전이 만든 `%APPDATA%\UsageTray` 폴더는 남으므로 직접 지워야 합니다.

이 앱은 Anthropic 또는 OpenAI와 관련이 없는 비공식 앱입니다.

문의: https://github.com/do-gongil/ai-usage-widget/issues

## English

Session Usage Widget (the "App") runs entirely on your PC. The developer collects no data.

- **Data read**: the access token in Claude Code's credentials file (`%USERPROFILE%\.claude\.credentials.json`), used only to query Claude usage; and Codex session logs (`%USERPROFILE%\.codex\sessions`), read locally.
- **Claude Code instant refresh (optional, off by default)**: when enabled from the tray menu, the App changes the `statusLine` command in Claude Code's settings (`%USERPROFILE%\.claude\settings.json`; the previous file is backed up as `settings.json.usagewidget.bak`, and turning it off restores the original command). Claude Code then writes usage values to `%USERPROFILE%\.claude\claude-live.json`, which the App only reads. This file never leaves your PC.
- **Network**: the token is sent only to Anthropic's usage endpoint (`https://api.anthropic.com/api/oauth/usage`). Nothing is sent anywhere else, including to the developer.
- **Stored data**: window position, display settings and the last usage values, kept only in the App's private folder on your PC (`%LOCALAPPDATA%\Packages\do-gongil.SessionUsageWidget_<ID>\LocalCache\Roaming\UsageTray`). The token is never stored by the App.
- **No telemetry, analytics, ads, or third-party sharing.**
- **Deletion**: uninstalling the App deletes that folder, including settings and the last usage values. Codex files and Claude Code credentials are left untouched. If you enabled instant refresh, turn it off from the tray menu before uninstalling so `settings.json` is restored; `claude-live.json` remains and can be deleted manually. If you previously used the Python version from GitHub, the `%APPDATA%\UsageTray` folder it created remains and must be deleted manually.

This App is unofficial and not affiliated with Anthropic or OpenAI.

Contact: https://github.com/do-gongil/ai-usage-widget/issues
