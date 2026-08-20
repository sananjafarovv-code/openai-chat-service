# OpenAI Chat Sessions API

Рабочий REST API на FastAPI для независимых чат-сессий с OpenAI. Сервис хранит историю диалога в SQLite, позволяет сбрасывать активный контекст без смены session ID, поддерживает выбор модели для отдельного сообщения, фиксирует token usage и считает накопленную стоимость активной generation.

## Стек

- Python 3.12
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
OPENAI_MODEL=gpt-5.6-luna
OPENAI_REASONING_EFFORT=none
OPENAI_REASONING_CONTEXT=current_turn
OPENAI_MAX_OUTPUT_TOKENS=1024
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

Модель сессии используется по умолчанию. Для одного сообщения её можно переопределить, не меняя default сессии:

```bash
curl -X POST http://127.0.0.1:8000/sessions/SESSION_ID/messages \
  -H "Content-Type: application/json" \
  -d '{"content":"Дай более подробный ответ.","model":"gpt-5.6-terra"}'
```

Сервис загрузит историю только активной generation, добавит новое сообщение, выполнит запрос через OpenAI Responses API и атомарно сохранит user/assistant messages, usage и стоимость. Ответ содержит сообщение ассистента, фактически использованную модель, usage текущего запроса и обновлённые итоги сессии. Сообщения и usage одного запроса связаны общим `interaction_id`.

Сообщения одной сессии сериализуются внутри процесса: параллельный запрос дождётся предыдущего и получит уже обновлённый контекст. Разные сессии могут обрабатываться параллельно.

### 3. Сбросить активный контекст

```bash
curl -X POST http://127.0.0.1:8000/sessions/SESSION_ID/reset
```

Session ID и модель по умолчанию сохраняются. `current_generation` увеличивается, активные token totals и cost обнуляются, а следующее сообщение отправляется без старого контекста. Предыдущие messages и usage физически не удаляются: они остаются в БД как архивные generations.

Reset и отправка сообщения используют один per-session lock, поэтому внутри процесса не могут перемешать данные двух generations.

### 4. Получить активную историю сессии

```bash
curl http://127.0.0.1:8000/sessions/SESSION_ID
```

Ответ содержит `current_generation`, её сообщения в стабильном порядке `sequence_number`, активные usage-записи и накопленные `total_input_tokens`, `total_output_tokens`, `total_cost`. Архивные generations в текущую историю не включаются.

## Модель и расчёт стоимости

По умолчанию используется `gpt-5.6-luna`. Для создания сессии и разового model override поддерживаются:

| Модель | Input / 1M | Cached input / 1M | Cache write / 1M | Output / 1M |
| --- | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` | `$0.20` | `$0.02` | `$0.25` | `$1.20` |
| `gpt-5.6-terra` | `$2.00` | `$0.20` | `$2.50` | `$12.00` |

Формула:

```text
uncached_input_cost = uncached_input_tokens / 1_000_000 × input_price
cached_input_cost   = cached_input_tokens / 1_000_000 × cached_input_price
cache_write_cost    = cache_write_tokens / 1_000_000 × cache_write_price
output_cost         = output_tokens / 1_000_000 × output_price
total_cost          = все input-компоненты + output_cost
```

Для запросов свыше 272K входных токенов применяется коэффициент `2×` к input и `1.5×` к output. Денежные значения рассчитываются через `Decimal`. Каждая usage-запись хранит generation, фактически использованную модель, подробный token usage, применённые тарифы и рассчитанную стоимость, поэтому смена модели и последующее изменение конфигурации не портят историю. Актуальные тарифы взяты из официальных страниц [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) и [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra).

Responses API вызывается с `store=false`, `reasoning.context=current_turn` и `reasoning.effort=none` по умолчанию. Поэтому сервис управляет текстовым контекстом локально и не зависит от серверного хранения OpenAI. `current_turn` намеренно зафиксирован для текстового MVP; reasoning effort и максимальный размер ответа задаются через окружение.

## Ошибки

- `404 Not Found` — сессия не существует;
- `422 Unprocessable Content` — пустое сообщение или модель без настроенного тарифа;
- `409 Conflict` — generation сессии изменилась во время обработки сообщения;
- `429 Too Many Requests` — rate limit OpenAI;
- `502 Bad Gateway` — OpenAI вернул ошибку или некорректный ответ;
- `503 Service Unavailable` — ключ не настроен, отсутствуют API-кредиты либо OpenAI недоступен;
- `504 Gateway Timeout` — таймаут OpenAI;
- `500 Internal Server Error` — непредвиденная ошибка БД или приложения.

При ошибке OpenAI пользовательское сообщение, незавершённый ответ и стоимость не сохраняются. Сообщения и usage успешного ответа фиксируются одной транзакцией БД.

## Тесты

```bash
pytest -q
```

Тесты не расходуют API-баланс: OpenAI-клиент подменяется детерминированной реализацией. Проверяются создание и изоляция сессий, reset с архивированием generations, чистый контекст после reset, model override и pricing фактической модели, сериализация конкурентных сообщений, detailed usage/cost, OpenAI adapter, HTTP-ошибки, foreign keys, миграции с существующими данными и отсутствие частично сохранённых ответов.

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
- архивные generations сохраняются в БД, но отдельный endpoint для их просмотра не входит в текущий scope;
- per-session lock действует внутри одного процесса; для нескольких workers нужен внешний lock или PostgreSQL;
- повтор одного POST-запроса клиентом не защищён idempotency key;
- SQLite подходит для тестового задания, но для production с параллельными записями предпочтительнее PostgreSQL.
