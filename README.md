# OpenAI Chat Sessions API

Рабочий REST API на FastAPI для независимых чат-сессий с OpenAI. Сервис хранит историю диалога в SQLite, передаёт её модели при каждом новом сообщении, фиксирует token usage каждого взаимодействия и считает накопленную стоимость сессии.

## Стек

- Python 3.12 (код совместим с Python 3.9+)
- FastAPI и Pydantic
- SQLite и SQLAlchemy 2.0
- Alembic
- официальный OpenAI Python SDK и Responses API
- pytest

## Быстрый запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Добавьте API-ключ в локальный `.env`:

```dotenv
OPENAI_API_KEY=your_api_key_here
```

Настоящий ключ нельзя добавлять в `.env.example`, README или Git. Файлы `.env*`, кроме безопасного примера, исключены через `.gitignore`.

Примените миграции и запустите сервер:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Документация Swagger: `http://127.0.0.1:8000/docs`.

Проверка состояния:

```bash
curl http://127.0.0.1:8000/health
```

## REST API и примеры запросов

### 1. Создать сессию

Модель можно не передавать — будет использована `OPENAI_MODEL` из окружения.

```bash
curl -X POST http://127.0.0.1:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"title":"Test conversation"}'
```

Ответ содержит UUID сессии, модель, нулевые счётчики usage и даты.

### 2. Отправить сообщение

Подставьте UUID из первого ответа вместо `SESSION_ID`:

```bash
curl -X POST http://127.0.0.1:8000/sessions/SESSION_ID/messages \
  -H "Content-Type: application/json" \
  -d '{"content":"Объясни принцип работы REST API в двух предложениях."}'
```

Сервис загрузит историю только этой сессии, добавит новое сообщение, выполнит запрос через OpenAI Responses API и атомарно сохранит user/assistant messages, usage и стоимость. Ответ содержит сообщение ассистента, usage текущего запроса и обновлённые итоги сессии.

### 3. Получить сессию с полной историей

```bash
curl http://127.0.0.1:8000/sessions/SESSION_ID
```

Ответ содержит сообщения в стабильном порядке `sequence_number`, все usage-записи и накопленные `total_input_tokens`, `total_output_tokens`, `total_cost`.

## Модель и расчёт стоимости

По умолчанию используется `gpt-5.6-luna`. Настроенные тарифы:

- input: `$0.20` за 1 млн токенов;
- output: `$1.20` за 1 млн токенов.

Формула:

```text
input_cost  = input_tokens  / 1_000_000 × input_price
output_cost = output_tokens / 1_000_000 × output_price
total_cost  = input_cost + output_cost
```

Денежные значения рассчитываются через `Decimal`. Каждая usage-запись хранит модель, применённые тарифы и рассчитанную стоимость, поэтому последующее изменение конфигурации не меняет старую историю. Актуальные тарифы взяты из [официальной страницы GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

## Ошибки

- `404 Not Found` — сессия не существует;
- `422 Unprocessable Content` — пустое сообщение или модель без настроенного тарифа;
- `502 Bad Gateway` — OpenAI вернул ошибку или некорректный ответ;
- `503 Service Unavailable` — `OPENAI_API_KEY` не настроен;
- `500 Internal Server Error` — непредвиденная ошибка БД или приложения.

При ошибке OpenAI пользовательское сообщение, незавершённый ответ и стоимость не сохраняются. Сообщения и usage успешного ответа фиксируются одной транзакцией БД.

## Тесты

```bash
pytest -q
```

Интеграционные тесты не расходуют API-баланс: OpenAI-клиент подменяется детерминированной реализацией. Проверяются создание сессии, сохранение и повторная передача контекста, изоляция ошибок, usage/cost, валидация и отсутствие частично сохранённых данных.

## Структура

```text
app/
  api/                  # routes и зависимости FastAPI
  core/                 # конфигурация и прикладные исключения
  db/                   # SQLAlchemy-модели и подключение к БД
  repositories/         # операции сохранения и чтения
  schemas/              # входные и выходные Pydantic-схемы
  services/             # chat orchestration, OpenAI adapter, pricing
migrations/             # Alembic-миграции
tests/                  # unit и API integration tests
```

## Известные ограничения MVP

- нет авторизации и разделения пользователей;
- нет streaming-ответов и автоматического сокращения длинного контекста;
- сообщения одной сессии должны отправляться последовательно;
- повтор одного POST-запроса клиентом не защищён idempotency key;
- cached input тарифицируется как обычный input, поскольку отдельный cached token usage в схеме MVP не хранится;
- специальный повышающий коэффициент для промптов свыше 272K токенов не реализован;
- SQLite подходит для тестового задания, но для production с параллельными записями предпочтительнее PostgreSQL.
