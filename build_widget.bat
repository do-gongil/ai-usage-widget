@echo off
REM Builds the C# PiP widget into dist\UsageWidget\UsageWidget.exe (self-contained, no .NET install needed)
dotnet test UsageWidget.Tests || exit /b 1
dotnet publish UsageWidget -c Release -r win-x64 -p:Platform=x64 -o dist\UsageWidget || exit /b 1
