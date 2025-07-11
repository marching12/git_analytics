@echo off
echo.
echo =================================
echo  GitHub PUSH Script
echo =================================
echo.

:: 1. requirements.txt 자동 업데이트
echo Updating requirements.txt...
pip freeze > requirements.txt
echo requirements.txt updated successfully.
echo.

:: 2. 커밋 메시지를 입력받습니다.
set /p commit_message="Enter commit message: "

:: 만약 메시지를 입력하지 않았다면 기본 메시지를 사용합니다.
if "%commit_message%"=="" set commit_message=Update files

echo.
echo Staging all files...
git add .

echo.
echo Committing with message: "%commit_message%"
git commit -m "%commit_message%"

echo.
:: 현재 브랜치 이름을 자동으로 가져옵니다.
for /f "delims=" %%i in ('git branch --show-current') do set current_branch=%%i

echo Pushing to origin %current_branch%...
git push origin %current_branch%

echo.
echo =================================
echo  Push Complete!
echo =================================
echo.
pause