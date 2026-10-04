# Campus Helpdesk

Campus Helpdesk — учебный серверный продукт для регистрации и обработки
обращений во внутреннюю техническую поддержку. Проект разрабатывается командой
из двух участников в рамках курса «Разработка безопасного программного
обеспечения».

## Навигация по материалам EK1

- [Паспорт проекта](PROJECT.md)
- [Требования безопасности](docs/SECURITY_REQUIREMENTS.md)
- [Модель угроз](docs/THREAT_MODEL.md)
- [Проектные решения безопасности](docs/SECURITY_DECISIONS.md)
- [Вклад участников](CONTRIBUTIONS.md)
- [Использование генеративного ИИ](AI_USAGE.md)
- [Сценарий защиты](docs/DEFENSE_SCRIPT.md)
- [Чек-лист готовности](docs/DEFENSE_CHECKLIST.md)

## Текущий статус

Минимальная техническая основа реализована и проверена локально: приложение
запускается, endpoint `GET /health` отвечает `200`, вход выдаёт JWT, а шесть
автоматизированных тестов проходят. Все оставшиеся места с маркером `TODO`
должны быть проверены и заполнены командой до сдачи.

## Стек

- Python 3.12+
- FastAPI
- SQLite
- SQLAlchemy
- pytest

## Быстрый запуск

Требуется Python 3.12 или новее.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
export JWT_SECRET='replace-with-at-least-32-random-characters'
export SEED_PASSWORD='replace-with-at-least-10-characters'
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Данные сохраняются в локальном файле SQLite `campus_helpdesk.db`. Отдельный
сервер базы данных и дополнительная инфраструктура не требуются.

После запуска:

- health-check: <http://127.0.0.1:8000/health>;
- Swagger UI: <http://127.0.0.1:8000/docs>.

Учебные аккаунты создаются при первом запуске:

- `user1@campus.local` — роль `User`;
- `user2@campus.local` — роль `User`;
- `specialist@campus.local` — роль `Specialist`.

Для всех используется пароль из `SEED_PASSWORD`.

## Проверка

```bash
python -m pytest
```

Проверяются запуск, аутентификация, запрет чтения чужого обращения, сокрытие
внутренних заметок, полномочия специалиста и повторное открытие обращения.
