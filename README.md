# OrganizePro 0.0.1

**A local-first, multi-source file organizer for Windows.** OrganizePro watches multiple folders independently, applies source-specific category rules, and routes files either into category folders inside the source or to a separate destination. It is designed to be predictable, reversible, and safe by default.

[English](#english) · [فارسی](#فارسی)

---

# English

## Overview

OrganizePro helps keep Downloads, Desktop, work folders, media libraries, and other directories organized without uploading files to a cloud service. The desktop process runs locally and exposes a private dashboard on `127.0.0.1`.

### Core capabilities

- **Multiple independent sources:** add as many source folders as needed. Each source has its own name, enabled state, destination mode, recursion setting, and category/extension rules.
- **Per-source destinations:** organize in place (default) or route files into a dedicated destination. A destination is optional and can be configured independently for every source.
- **Concurrent monitoring:** each enabled source gets its own monitor, event queue, baseline, and organizer configuration.
- **Source-specific categories:** define different categories and extensions for each source. A Downloads source can use Documents/Pictures/Installers while a media source uses Movies/Series/Audio.
- **Safe new-file monitoring:** each monitor establishes a baseline when started; pre-existing files are not moved by monitoring. Use the explicit preview and confirmation workflow for existing files.
- **Batch preview and Dry Run:** inspect planned actions before moving existing files.
- **Collision handling:** rename, skip, compare content, or explicitly confirmed replacement with a recoverable backup.
- **Undo and activity history:** review completed operations and undo eligible moves.
- **Project protection:** common development metadata, build outputs, temporary downloads, symlinks, and configured exclusions are protected.
- **Windows integration:** optional startup registration, system tray, and desktop notifications.
- **Local-only dashboard:** loopback binding and request authorization; no public/LAN web server.
- **Portable settings model:** settings and history are stored in the user's application-data directory.

## Quick start

Requirements: Windows 10/11, Python 3.10+, and a modern browser. Python 3.13 is supported when all dependencies provide compatible wheels.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Open **Settings → Source Manager**, add a source, and choose in-place organization or a separate destination. Add more sources as needed and start monitoring from the dashboard.

## Source and destination behavior

Each source is configured independently: the source folder identifies input files; a separate destination is optional; categories and extensions belong to that source; disabled sources are not monitored. Do not configure a source equal to or nested inside its destination. OrganizePro excludes its own category output folders during in-place operation.

## Safety model

- Monitoring uses **New Files Only** semantics: a baseline is captured before monitoring accepts new filesystem events.
- Existing files require the explicit batch preview / confirmation flow.
- Unknown extensions and temporary/incomplete download suffixes are skipped by default.
- Project files and common build/cache directories are protected by default.
- Symlinks and junctions are not followed.
- Existing destination files are not silently overwritten.
- Replacement is opt-in, requires explicit confirmation, and retains a backup for recovery.
- Cross-volume moves use staging and verification; the source is removed only after the destination is committed and verified.

## Dashboard

Aggregate monitoring status, Source Manager, category/extension rules, existing-file preview and Dry Run, activity history, CSV export, Undo, and runtime/collision/exclusion/startup/notification settings.

## Build a Windows executable

Run in PowerShell on Windows:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

The script uses the active Python interpreter, installs dependencies, runs tests, and creates a windowed PyInstaller executable at `dist\OrganizePro.exe`. Use `-OneDir` for a folder-based build or `-Clean` for a clean rebuild.

## CLI

```powershell
python main.py --help
python main.py --version
python main.py --no-browser
python main.py --tray
python main.py --dry-run
python main.py --once --confirm
```

## Data and privacy

On Windows, application data is stored under `%APPDATA%\OrganizePro` by default. Set `ORGANIZEPRO_DATA_DIR` to use an isolated data directory for development or tests. Files are processed locally; no cloud account is required.

## Development and tests

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
node --check app/web/frontend/app.js
python -m compileall -q main.py app tests
```

Use temporary directories and synthetic files for tests. Never run destructive organizer tests against a real Downloads/Desktop folder.

## Project structure

```text
OrganizePro/
├── main.py
├── app/ (config, core, desktop, web, controller.py)
├── assets/
├── tests/
├── requirements.txt
├── OrganizePro.spec
└── build_windows.ps1
```

## Roadmap

- [x] In-place organization and optional destination routing
- [x] Remove Minecraft from default categories
- [x] Multi-source configuration model and independent monitor services
- [x] Source-specific category rules
- [ ] Full source editor for changing category rules after creation
- [ ] Per-source batch preview and execution controls
- [ ] Import/export source profiles
- [ ] Signed Windows installer and automated release artifacts
- [ ] Localization and accessibility review

## Contributing

Fork the repository, create a focused branch, install dependencies in a virtual environment, add tests for behavior changes, run the test suite and JavaScript syntax check, then open a pull request with reproduction steps.

## License

A license file must be selected by the repository owner before redistribution. Until then, all rights are reserved; do not assume the project is MIT-licensed.

---

# فارسی

## معرفی

**OrganizePro** ابزاری محلی و چندمنبعی برای مرتب‌سازی خودکار فایل‌ها در ویندوز است. برنامه می‌تواند چند پوشه مانند Downloads، Desktop، پوشه پروژه‌ها یا آرشیو رسانه‌ای را مستقل پایش کند. فایل‌ها روی دستگاه شما پردازش می‌شوند و نیازی به آپلود اطلاعات به سرویس ابری نیست.

## امکانات

- افزودن چند پوشه مبدأ مستقل با تنظیمات جداگانه.
- تعریف دسته‌بندی و پسوندهای اختصاصی برای هر Source.
- مرتب‌سازی داخل همان پوشه مبدأ یا انتقال به مقصد جداگانه و اختیاری.
- پایش هم‌زمان هر Source با سرویس و صف رویداد مستقل.
- پیش‌نمایش و Dry Run برای فایل‌های موجود.
- مدیریت تداخل نام، مقایسه محتوا و جایگزینی با تأیید صریح و نسخه پشتیبان.
- تاریخچه عملیات و Undo برای عملیات واجد شرایط.
- محافظت از فایل‌های پروژه، پوشه‌های Build/Cache و فایل‌های موقت.
- داشبورد محلی، System Tray، اعلان و اجرای خودکار ویندوز.

## نصب سریع

پیش‌نیاز: Windows 10/11 و Python 3.10 یا جدیدتر.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

در داشبورد به **Settings → Source Manager** بروید، پوشه مبدأ را اضافه کنید و مشخص کنید فایل‌ها داخل همان پوشه مرتب شوند یا به مقصد جداگانه منتقل شوند. برای هر پوشه می‌توانید دسته‌بندی مخصوص خودش را داشته باشید.

## منطق مبدأ و مقصد

هر Source تنظیمات مستقل دارد. مقصد جداگانه اختیاری است؛ اگر غیرفعال باشد، پوشه‌های دسته‌بندی داخل خود Source ساخته می‌شوند. اگر فعال باشد، فایل‌ها به دسته‌بندی‌های داخل Destination منتقل می‌شوند. مبدأ نباید با مقصد یکسان باشد یا داخل مقصد قرار بگیرد.

## ایمنی

- پایش عادی فقط فایل‌های جدید را پردازش می‌کند.
- برای فایل‌های قبلی باید پیش‌نمایش و تأیید صریح انجام شود.
- فایل‌های ناشناخته و دانلودهای ناقص به‌صورت پیش‌فرض دست‌نخورده می‌مانند.
- فایل‌های پروژه و پوشه‌های Build/Cache محافظت می‌شوند.
- Symlink و Junction دنبال نمی‌شوند.
- فایل مقصد بدون اجازه جایگزین نمی‌شود.
- Replace نیازمند فعال‌سازی و تأیید است و نسخه پشتیبان نگه می‌دارد.

## ساخت EXE

در PowerShell و پوشه پروژه:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

خروجی پیش‌فرض `dist\OrganizePro.exe` است. برای خروجی پوشه‌ای از `-OneDir` و برای Build تمیز از `-Clean` استفاده کنید.

## حریم خصوصی

در ویندوز تنظیمات، تاریخچه و گزارش‌ها به‌طور پیش‌فرض در `%APPDATA%\OrganizePro` ذخیره می‌شوند. با متغیر `ORGANIZEPRO_DATA_DIR` می‌توانید مسیر داده را برای توسعه یا تست تغییر دهید. فایل‌ها به‌صورت محلی پردازش می‌شوند.

## توسعه و تست

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
node --check app/web/frontend/app.js
python -m compileall -q main.py app tests
```

برای تست از پوشه‌های موقت استفاده کنید و تست مخرب را روی Downloads یا Desktop واقعی اجرا نکنید.

## مجوز

تا زمان افزودن فایل LICENSE توسط مالک مخزن، مجوز MIT یا مجوز آزاد دیگری را فرض نکنید؛ حقوق انتشار و بازتوزیع محفوظ است.
