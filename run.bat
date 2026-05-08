@echo off
chcp 65001 >nul
title Biotech Daily

if "%ANTHROPIC_API_KEY%"=="" (
    echo [ERROR] ANTHROPIC_API_KEY 환경변수가 등록되어 있지 않습니다.
    echo.
    echo 1회만 cmd에서:
    echo     setx ANTHROPIC_API_KEY "sk-ant-..."
    echo 그 후 새 cmd 창 열고 이 .bat 다시 실행하세요.
    echo.
    pause
    exit /b 1
)

cd /d "%~dp0"
python biotech_daily.py

if errorlevel 1 (
    echo.
    echo [에러 발생 — 위 메시지 확인 후 아무 키나 누르세요]
    pause
)
