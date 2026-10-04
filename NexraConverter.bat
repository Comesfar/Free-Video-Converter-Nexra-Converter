@echo off
chcp 65001 >nul
title Nexra Video Compressor
cd /d "%~dp0"

echo Nexra Video Compressor başlatılıyor...
python main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [HATA] Uygulama calisirken bir sorun olustu.
    echo Gerekli kutuphaneleri yuklemek icin: pip install -r requirements.txt
    echo.
    pause
)
