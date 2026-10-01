@echo off
rem Gera dist\ConversorAtestados.exe (executavel unico, sem janela de terminal).
rem O ambiente de desenvolvimento fica em %LOCALAPPDATA%\conversor-atestados\venv porque
rem alguns pacotes do PyInstaller passam do limite de 260 caracteres do Windows em pastas fundas.
setlocal
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\conversor-atestados\venv"

if not exist "%VENV%\Scripts\python.exe" (
    echo Criando o ambiente de desenvolvimento em %VENV% ...
    python -m venv "%VENV%" || goto erro
    "%VENV%\Scripts\python.exe" -m pip install -r requirements-dev.txt || goto erro
)

echo Rodando os testes...
"%VENV%\Scripts\python.exe" -m pytest -q || goto erro

echo Gerando o executavel...
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean ^
    --workpath "%TEMP%\conversor-atestados-build" --distpath "%~dp0dist" ConversorAtestados.spec || goto erro

echo.
echo Pronto: %~dp0dist\ConversorAtestados.exe
exit /b 0

:erro
echo.
echo Falhou. Veja as mensagens acima.
exit /b 1
