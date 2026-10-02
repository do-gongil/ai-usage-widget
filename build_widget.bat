@echo off
REM Builds the C# PiP widget: tests -> dist\release\UsageWidget\ (self-contained) -> dist\ai-usage-widget-win-x64.zip
REM Publishes to dist\release so a copy you are running elsewhere (e.g. dist\UsageWidget) is never touched.
dotnet test UsageWidget.Tests || exit /b 1
if exist dist\release rmdir /s /q dist\release
dotnet publish UsageWidget -c Release -r win-x64 -p:Platform=x64 -o dist\release\UsageWidget || exit /b 1
REM Windows built-in tar (bsdtar): PS 5.1 Compress-Archive stores backslash paths that some unzip tools mangle
if exist dist\ai-usage-widget-win-x64.zip del dist\ai-usage-widget-win-x64.zip
tar -a -c -f dist\ai-usage-widget-win-x64.zip -C dist\release UsageWidget || exit /b 1
echo Built dist\ai-usage-widget-win-x64.zip
REM Installer (needs Inno Setup 6: winget install JRSoftware.InnoSetup). Skipped if not installed.
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" ( echo Inno Setup not found - skipped installer & exit /b 0 )
for /f "tokens=3 delims=<>" %%v in ('findstr /c:"<Version>" UsageWidget\UsageWidget.csproj') do set "APPVER=%%v"
"%ISCC%" /Q /DAppVersion=%APPVER% installer.iss || exit /b 1
echo Built dist\ai-usage-widget-setup.exe (v%APPVER%)
