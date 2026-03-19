@echo off
chcp 65001 > nul
title Offi-Stretchリスト管理

echo ==========================================
echo   Offi-Stretchリスト管理 起動中...
echo ==========================================
echo.

:: IPアドレスを取得して表示
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set IP=%%a
    goto :found
)
:found
set IP=%IP: =%

echo 【アクセスURL】
echo   このPC    : http://localhost:8501
echo   他のPC/スマホ: http://%IP%:8501
echo.
echo ※ 同じWi-Fi内のPCやスマホから上記URLを開いてください
echo ※ このウィンドウを閉じるとアプリが停止します
echo.

:: ブラウザを少し遅らせて開く（Streamlit起動を待つため）
start "" timeout /t 3 /nobreak > nul
start "" http://localhost:8501

:: Streamlit起動（LAN公開モード）
cd /d "%~dp0"
python -m streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true

pause
