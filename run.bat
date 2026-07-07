@echo off
where python >nul 2>nul
if %errorlevel%==0 (
    set PY=python
) else (
    set PY="C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe"
)

cd /d "%~dp0"
echo 檢查/安裝必要套件...
%PY% -m pip install -q -r requirements.txt
echo 啟動中，會自動開瀏覽器...
%PY% -m streamlit run app.py
pause
