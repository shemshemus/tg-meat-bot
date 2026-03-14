# AI Marketing & Order Copilot for a Local Food Business

A backend system for a small meat-products business that manages products, captures customer orders via Telegram, and generates AI-powered marketing content.

## Features

- **Product Management** — CRUD API for products with categories, pricing, and stock tracking
- **Order System** — Capture orders via REST API or Telegram bot with status workflow (new → confirmed → completed)
- **Telegram Bot** — Customers browse products, check prices, and place orders through natural chat messages like "2 kg beef sausage"
- **AI Marketing** — Generate ad copy for products with selectable tone (friendly, professional, funny, urgent). Rule-based fallback works without an API key
- **Analytics** — Business summary endpoint with order breakdowns and top-selling products

## Tech Stack

- **Python 3.11** / **FastAPI** — async-ready web framework with automatic validation and OpenAPI docs
- **PostgreSQL** — relational database with foreign key constraints
- **SQLAlchemy** — ORM for database operations
- **Pydantic** — request/response validation and serialization
- **python-telegram-bot** — Telegram Bot API integration (polling mode)
- **OpenAI API** — optional LLM integration for marketing content generation
- **Docker / Docker Compose** — containerized deployment

## Architecture

```
├── app/
│   ├── main.py              # FastAPI app + Telegram bot lifecycle
│   ├── config.py            # Environment-based settings (pydantic-settings)
│   ├── database.py          # SQLAlchemy engine, session factory, dependency
│   ├── models/models.py     # ORM models: Product, Order, MarketingPost
│   ├── schemas/schemas.py   # Pydantic schemas for request/response validation
│   ├── routes/              # HTTP endpoint handlers
│   │   ├── products.py      # GET/POST/PATCH /products
│   │   ├── orders.py        # GET/POST /orders, PATCH status
│   │   ├── marketing.py     # POST /marketing/generate-post
│   │   └── analytics.py     # GET /analytics/summary
│   ├── services/            # Business logic (reused by both API and bot)
│   │   ├── product_service.py
│   │   ├── order_service.py
│   │   └── ai_service.py    # Rule-based + optional OpenAI
│   └── bot/
│       └── telegram_bot.py  # Telegram command & message handlers
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

**Design principle:** Routes handle HTTP wiring, services contain business logic, models define data. The Telegram bot and API routes share the same services and database.

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
# Prerequisites: Python 3.11+, PostgreSQL running locally

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
| `TELEGRAM_BOT_TOKEN` | No | From @BotFather — bot disabled if not set |
| `OPENAI_API_KEY` | No | For AI-generated marketing posts — falls back to templates |

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
