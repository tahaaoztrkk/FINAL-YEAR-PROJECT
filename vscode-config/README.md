# VS Code yapılandırması

Bu klasördeki dört dosyayı proje kökündeki `.vscode` klasörüne kopyalayın:

```powershell
New-Item -ItemType Directory -Force .vscode
Copy-Item vscode-config\*.json .vscode\
```

Kopyaladıktan sonra bu klasörü silebilirsiniz.

Ne sağlıyorlar:

- `settings.json` — Python yorumlayıcısı `backend/.venv`'e ayarlanır, pytest
  keşfi açılır, kayıtta ruff ile biçimlendirme yapılır
- `extensions.json` — ekibin kuracağı eklentiler (Python, Pylance, Ruff,
  ESLint, Prettier, Jupyter)
- `launch.json` — `F5` ile çalışan hazır yapılandırmalar: backend, simülasyon,
  testler
- `tasks.json` — `Ctrl+Shift+P` → `Tasks: Run Task`: frontend dev sunucusu,
  lint, sözleşme tiplerini üretme
