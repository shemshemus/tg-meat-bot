# AI Marketing & Order Copilot for a Local Food Business

A backend system for a small meat-products business that manages products, captures customer orders via Telegram, and generates AI-powered marketing content.

## Features

- **Product Management** — CRUD API for products with categories, pricing, and stock tracking
- **Order System** — Capture orders via REST API or Telegram bot with status workflow (new → confirmed → completed)
- **Telegram Bot** — Customers browse products, check prices, and place orders through natural chat messages like "2 kg beef sausage"
- **AI Marketing** — Generate ad copy for products with selectable tone (friendly, professional, funny, urgent). Rule-based fallback works without an API key
- **Analytics** — Business summary endpoint with order breakdowns and top-selling products
- **Redis Caching** — Persistent user state, product caching, and AI response memoization with graceful degradation

## Tech Stack

- **Python 3.11** / **FastAPI** — async-ready web framework with automatic validation and OpenAPI docs
- **PostgreSQL** — relational database with foreign key constraints
- **Redis** — in-memory cache for products, analytics, marketing text, and persistent user state
- **SQLAlchemy** — ORM for database operations
- **Pydantic** — request/response validation and serialization
- **python-telegram-bot** — Telegram Bot API integration (polling mode)
- **OpenAI API** — optional LLM integration for marketing content generation
- **Docker / Docker Compose** — containerized deployment

## Architecture

```
├── app/
│   ├── main.py              # FastAPI app + Telegram bot lifecycle + Redis init
│   ├── config.py            # Environment-based settings (pydantic-settings)
│   ├── database.py          # SQLAlchemy engine, session factory, dependency
│   ├── models/models.py     # ORM models: Product, Order, MarketingPost
│   ├── schemas/schemas.py   # Pydantic schemas for request/response validation
│   ├── routes/              # HTTP endpoint handlers
│   │   ├── products.py      # GET/POST/PATCH /products
│   │   ├── orders.py        # GET/POST /orders, PATCH status
│   │   ├── marketing.py     # POST /marketing/generate-post
│   │   └── analytics.py     # GET /analytics/summary (cached 1h)
│   ├── services/            # Business logic (reused by both API and bot)
│   │   ├── product_service.py   # Product CRUD with Redis caching
│   │   ├── order_service.py
│   │   ├── ai_service.py        # Rule-based + optional OpenAI (memoized)
│   │   └── cache_service.py     # Redis wrapper with graceful degradation
│   └── bot/
│       └── telegram_bot.py  # Telegram command & message handlers
├── Dockerfile
├── docker-compose.yml       # PostgreSQL + Redis + API
├── requirements.txt
└── .env.example
```

**Design principle:** Routes handle HTTP wiring, services contain business logic, models define data. The Telegram bot and API routes share the same services and database. Redis provides caching and persistent state with graceful fallback to in-memory when unavailable.

## Quick Start

### With Docker (recommended)

```bash
cp .env.example .env
# Edit .env — add TELEGRAM_BOT_TOKEN (optional), OPENAI_API_KEY (optional)

docker compose up --build
```

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Without Docker

```bash
# Prerequisites: Python 3.11+, PostgreSQL running locally, Redis running locally

cp .env.example .env
# Edit .env with your database URL and optional tokens

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create the database
createdb meat_bot

uvicorn app.main:app --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/products/` | List products (paginated) |
| POST | `/products/` | Create a product |
| GET | `/products/{id}` | Get a product |
| PATCH | `/products/{id}` | Update a product (partial) |
| GET | `/orders/` | List orders (newest first) |
| POST | `/orders/` | Create an order |
| GET | `/orders/{id}` | Get an order |
| PATCH | `/orders/{id}/status` | Update order status |
| POST | `/marketing/generate-post` | Generate marketing text for a product |
| GET | `/marketing/posts` | List generated posts |
| GET | `/analytics/summary` | Business stats summary |

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/products` | List available products |
| `/price <name>` | Check a product's price |
| Free text (e.g., "2 kg beef sausage") | Place an order |

## Configuration

All settings are managed via environment variables (`.env` file):

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | No | Redis connection string (default: `redis://localhost:6379/0`) |
| `TELEGRAM_BOT_TOKEN` | No | From @BotFather — bot disabled if not set |
| `OPENAI_API_KEY` | No | For AI-generated marketing posts — falls back to templates |

## How Caching Works

Redis acts as a fast, persistent layer between the application and PostgreSQL. All caching uses the **cache-aside** pattern: check Redis first, query the database on miss, then store the result in Redis for subsequent requests.

### Flow 1: Product List (Cache-Aside)

```
User sends /products
  → Bot calls product_service.get_all()
    → Check Redis: GET "products:all:0:50"
      → HIT?  → Return cached list (skip DB entirely)
      → MISS? → Query PostgreSQL
               → Store in Redis with 5-min TTL
               → Return fresh list
```

### Flow 2: Promo Broadcast (Persistent State)

```
Every 1.5 days, JobQueue triggers send_promo_post()
  → Get users: SMEMBERS "promo:users"        ← survives restarts
  → Get last product: GET "promo:last_product_id"
  → Pick random product (skip last one)
  → For each user:
      → HGET "user:languages" <user_id>       ← language preference
      → Check Redis: GET "marketing:{id}:{tone}:{lang}"
        → HIT?  → Use cached marketing text
        → MISS? → Call AI / rule-based generator
                 → Cache result for 30 days
      → Send message to user
  → SET "promo:last_product_id" <new_id>
```

### Flow 3: Product Update (Write-Through Invalidation)

```
Admin PATCHes /products/5
  → product_service.update() writes to PostgreSQL
  → DEL "products:*" from Redis               ← immediate invalidation
  → Next /products request fetches fresh data from DB
```

### Cache Key Reference

| Key | Type | TTL | Purpose |
|-----|------|-----|---------|
| `products:all:{skip}:{limit}` | string (JSON) | 5 min | All products list |
| `products:{id}` | string (JSON) | 5 min | Single product |
| `analytics:summary` | string (JSON) | 1 hour | Analytics aggregation |
| `marketing:{product_id}:{tone}:{lang}` | string (JSON) | 30 days | AI-generated text |
| `user:languages` | hash | Persistent | user_id → "ru"/"en" |
| `promo:users` | set | Persistent | User IDs for broadcasts |
| `promo:last_product_id` | string | Persistent | Last promoted product |

## Concepts

### Key-Value Cache Pattern
Redis stores data as key→value pairs with optional TTL (time-to-live). When we need products, we check Redis first ("cache hit") — if missing or expired ("cache miss"), we query PostgreSQL and store the result in Redis for next time. This is called **cache-aside** (or "lazy loading"): the app manages the cache explicitly.

### Hash Maps for User State
Redis hashes (`HSET/HGET`) store user preferences as field→value pairs under one key. Like a Python dict living in Redis: `user:languages` → `{123: "ru", 456: "en"}`. Survives restarts, shared across processes.

### Sets for User Tracking
Redis sets (`SADD/SMEMBERS`) store unique user IDs for promo broadcasts. No duplicates, O(1) add/check, persistent across restarts.

### TTL-Based Cache Invalidation
Each cached value has an expiration. Products cache expires in 5 minutes (short — stock changes). Analytics expires in 1 hour (aggregations are expensive but don't need real-time). AI marketing text expires in 30 days (same input = same quality output).

### Write-Through Invalidation
When a product is created/updated via the API, we delete the products cache keys immediately so the next read fetches fresh data. This prevents stale cache without waiting for TTL.

### Graceful Degradation
Every Redis operation is wrapped in try/except. If Redis is down, the app continues working — just without caching. User state falls back to in-memory dicts (lost on restart, but functional). This means Redis is an optimization, not a hard dependency.

## Example Requests

```bash
# Create a product
curl -X POST http://localhost:8000/products/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Beef Sausage", "price_per_kg": 15.0, "category": "sausages", "description": "Traditional beef sausage", "ingredients": "beef, salt, pepper, garlic"}'

# Place an order
curl -X POST http://localhost:8000/orders/ \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1, "quantity_kg": 2.5, "customer_name": "Ali"}'

# Generate a marketing post
curl -X POST http://localhost:8000/marketing/generate-post \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1, "tone": "funny"}'

# View analytics
curl http://localhost:8000/analytics/summary
```

## Verification

1. `docker compose up --build` — Redis, PostgreSQL, API all start
2. `redis-cli ping` → PONG
3. Send `/start` to bot → `redis-cli SMEMBERS promo:users` shows your user ID
4. Choose language → `redis-cli HGET user:languages <your_id>` shows "ru" or "en"
5. Send `/products` twice → second request served from cache (check logs)
6. Create a product via API → `redis-cli GET products:all:0:50` returns nil (invalidated)
7. Wait 1 min → promo arrives in your language
8. `redis-cli GET promo:last_product_id` shows the promoted product ID
9. Restart the API → send `/products` → promo still knows your user ID and language
