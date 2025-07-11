@echo off
echo.
echo =================================
echo  GitHub PULL Script
echo =================================
echo.

:: 현재 브랜치 이름을 자동으로 가져옵니다.
for /f "delims=" %%i in ('git branch --show-current') do set current_branch=%%i

echo Pulling latest changes from origin/%current_branch%...
git pull origin %current_branch%

echo.
echo =================================
echo  Pull Complete!
echo =================================
echo.
pause