@echo off
rem Demo: llama-server (model) + backend + frontend, uc ayri pencerede.
rem Cift tiklayin. Kapatmak icin uc pencereyi de kapatin.
cd /d "%~dp0"

if not exist "llama\llama-server.exe" (
  echo llama\llama-server.exe bulunamadi. docs\setup.md, "Demo bilgisayari" bolumune bakin.
  pause
  exit /b 1
)
if not exist "models\turkish-gemma-aac-Q4_K_M.gguf" (
  echo models\turkish-gemma-aac-Q4_K_M.gguf bulunamadi. Modeli Drive'dan indirip models\ klasorune koyun.
  pause
  exit /b 1
)
if not exist "backend\.venv\Scripts\activate.bat" (
  echo backend\.venv yok. README'deki Backend kurulumunu yapin.
  pause
  exit /b 1
)

start "1 - model (llama-server)" cmd /k "llama\llama-server.exe -m models\turkish-gemma-aac-Q4_K_M.gguf -ngl 99 -c 2048 --parallel 5 --port 8080"
start "2 - backend" cmd /k "cd backend && call .venv\Scripts\activate.bat && set "EXPANDER_PROVIDER=llamacpp" && uvicorn gaze_aac.main:app --port 8010"
start "3 - frontend" cmd /k "cd frontend && npm run dev"

echo Model ve sunucular aciliyor, tarayici 15 saniye sonra acilacak...
timeout /t 15 /nobreak >nul
start "" http://127.0.0.1:5173
