@echo off
REM Compilar informe técnico AgroSmart Andino
REM Requiere: MiKTeX o TeX Live instalado

cd /d "%~dp0"

echo Compilando informe_tecnico.tex ...
pdflatex -interaction=nonstopmode informe_tecnico.tex
pdflatex -interaction=nonstopmode informe_tecnico.tex

if exist informe_tecnico.pdf (
    echo.
    echo [OK] informe_tecnico.pdf generado correctamente.
    echo Abriendo PDF...
    start informe_tecnico.pdf
) else (
    echo.
    echo [ERROR] No se pudo generar el PDF. Revisa informe_tecnico.log
)
