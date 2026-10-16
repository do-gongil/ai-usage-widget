# Session Usage Widget — 개인정보처리방침 / Privacy Policy

최종 수정: 2026-10-16

## 한국어

Session Usage Widget(이하 "앱")은 사용자의 PC에서만 동작하며, 개발자는 어떤 데이터도 수집하지 않습니다.

- **읽는 정보**
  - Claude Code 로그인 정보(`%USERPROFILE%\.claude\.credentials.json`)의 액세스 토큰: Claude 사용량을 조회하는 데만 씁니다.
  - Codex 세션 기록(`%USERPROFILE%\.codex\sessions`): 사용량 수치를 PC 안에서 읽기만 합니다.
- **네트워크 전송**: 위 토큰은 Anthropic의 사용량 조회 주소(`https://api.anthropic.com/api/oauth/usage`)에만 보냅니다. 그 밖의 서버(개발자 서버 포함)로는 아무것도 보내지 않습니다.
- **저장하는 정보**: 창 위치, 표시 설정, 마지막 사용량 수치를 PC 안의 앱 전용 폴더(`%LOCALAPPDATA%\Packages\do-gongil.SessionUsageWidget_<ID>\LocalCache\Roaming\UsageTray`)에만 저장합니다. 토큰은 저장하지 않습니다.
- **수집·분석·광고**: 사용 통계, 분석 도구, 광고, 제3자 공유가 모두 없습니다.
- **삭제**: 앱을 제거하면 위 폴더의 설정과 마지막 수치도 함께 삭제됩니다. 앱이 읽기만 하는 Claude Code·Codex 파일은 건드리지 않습니다. 이전에 GitHub의 Python 버전을 쓴 적이 있다면 그 버전이 만든 `%APPDATA%\UsageTray` 폴더는 남으므로 직접 지워야 합니다.

이 앱은 Anthropic 또는 OpenAI와 관련이 없는 비공식 앱입니다.

문의: https://github.com/do-gongil/ai-usage-widget/issues

## English

Session Usage Widget (the "App") runs entirely on your PC. The developer collects no data.

- **Data read**: the access token in Claude Code's credentials file (`%USERPROFILE%\.claude\.credentials.json`), used only to query Claude usage; and Codex session logs (`%USERPROFILE%\.codex\sessions`), read locally.
- **Network**: the token is sent only to Anthropic's usage endpoint (`https://api.anthropic.com/api/oauth/usage`). Nothing is sent anywhere else, including to the developer.
- **Stored data**: window position, display settings and the last usage values, kept only in the App's private folder on your PC (`%LOCALAPPDATA%\Packages\do-gongil.SessionUsageWidget_<ID>\LocalCache\Roaming\UsageTray`). The token is never stored by the App.
- **No telemetry, analytics, ads, or third-party sharing.**
- **Deletion**: uninstalling the App deletes that folder, including settings and the last usage values. Claude Code and Codex files, which the App only reads, are left untouched. If you previously used the Python version from GitHub, the `%APPDATA%\UsageTray` folder it created remains and must be deleted manually.

This App is unofficial and not affiliated with Anthropic or OpenAI.

Contact: https://github.com/do-gongil/ai-usage-widget/issues
