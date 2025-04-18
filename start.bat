@echo off
cd /d "D:/my_computer/Life/my_projects/my_investments"

:: активация виртуального окружения
call .venv\Scripts\activate.bat

:: запуск сервера
start "Flask Server" cmd /k "python app.py

:: задержка на 2 сек.
timeout /t 2 /nobreak >nul

:: открытие браузера
start "" "http://127.0.0.1:5000/"

