@echo off
REM Microsoft Store??MSIX ?⑦궎吏: tests -> dist\store\UsageWidget_<ver>_x64_Test\UsageWidget_<ver>_x64.msix
REM ?쒕챸 ?놁쓬(Store媛 ?쒕챸). 踰꾩쟾? UsageWidget.csproj <Version>怨?Package.appxmanifest Identity Version??媛숈씠 ?щ┛??
dotnet test UsageWidget.Tests || exit /b 1
if exist dist\store rmdir /s /q dist\store
dotnet publish UsageWidget -c Release -r win-x64 -p:Platform=x64 -p:GenerateAppxPackageOnBuild=true -p:AppxPackageDir=%~dp0dist\store\ || exit /b 1
echo Built MSIX in dist\store
