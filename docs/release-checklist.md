# 릴리스 체크리스트 (Store / C# 버전)

버전 `X.Y.Z` 기준. 레거시 Python 버전은 새 릴리스를 만들지 않습니다.

## 1. 버전 올리기 (세 곳을 같이)

- [ ] `UsageWidget/UsageWidget.csproj` → `<Version>X.Y.Z</Version>`
- [ ] `UsageWidget/Package.appxmanifest` → `<Identity ... Version="X.Y.Z.0" />` (Store는 이전 제출보다 큰 버전만 받음)
- [ ] `README.md` 첫 안내문의 `(vX.Y.Z, ...)`

## 2. 테스트

- [ ] `dotnet test UsageWidget.Tests`
- [ ] `usage_core.py`를 건드렸다면 `python test_usage_core.py`

## 3. 빌드

- [ ] `Package.appxmanifest`의 `Identity Name`·`Publisher`·`PublisherDisplayName`이 Partner Center 제품 ID 값과 같은지 확인 ([store-listing.md](store-listing.md) §0)
- [ ] `build_store.bat` 실행 (테스트 → `dist\store\UsageWidget_X.Y.Z.0_x64_Test\UsageWidget_X.Y.Z.0_x64.msix`)
- [ ] 서명하지 않은 패키지입니다(Store가 서명). 이 MSIX를 GitHub에 올리지 않습니다.

## 4. Partner Center 제출

- [ ] 새 제출 → "패키지"에 위 `.msix` 업로드
- [ ] 바뀐 내용이 있으면 목록 갱신: 설명·짧은 설명·키워드·스크린샷 ([store-listing.md](store-listing.md) §1–5)
- [ ] 개인정보처리방침 URL이 열리는지 확인: `docs/privacy.md`가 `main`에 있어야 함. 저장 위치·수집 항목이 바뀌었으면 privacy.md부터 고침
- [ ] "인증 참고 사항"에 runFullTrust 사유와 심사자용 테스트 안내 입력 (§6, §7)

## 5. 커밋·GitHub

- [ ] 버전 커밋을 `main`에 push하고 태그 `vX.Y.Z`
- [ ] GitHub 릴리스(선택): 제목 `vX.Y.Z (Store)`, 본문은 변경 내용 + Store 링크 `https://apps.microsoft.com/detail/9NN9GN3KMSWN`. 파일은 첨부하지 않음
