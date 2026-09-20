# Legal AI Backend Boilerplate 🚀

A production-grade, async **FastAPI** backend boilerplate engineered for AI/LegalTech applications, with **PostgreSQL** (for user management & authentication) and **Weaviate** (for vector storage & semantic search), designed for **1-click free deployment on [Render.com](https://render.com)**.

---

## 🌟 Key Features

- **FastAPI Framework**: Modern async architecture with Pydantic v2 validation, CORS configuration, and interactive documentation (`/docs`, `/redoc`).
- **PostgreSQL & Async SQLAlchemy 2.0**:
  - Asynchronous database access using `asyncpg` with connection pooling.
  - User model with UUID primary keys, password hashing via `Argon2` / `Bcrypt` (`pwdlib`).
  - Production migrations powered by **Alembic** (async ready).
- **Weaviate v4 Vector Database**:
  - Integration with Weaviate v4 Python client.
  - Supports **Weaviate Cloud Services (WCS)** free sandbox or local Docker containers.
  - Hybrid search (BM25 keyword + semantic vector), near-vector search, and collection schema setup.
  - **Resilient boot**: The server starts gracefully even before vector credentials are fully configured.
- **Authentication & Security**:
  - Secure JSON login (`/api/v1/auth/login`) and OAuth2 password flow (`/api/v1/auth/login/oauth`).
  - JWT token generation, verification, and protected route dependencies (`get_current_active_user`).
  - Self-service profile updates (`/api/v1/users/me`).
- **Render.com Ready**:
  - `render.yaml` Blueprint for free 1-click deployment (FastAPI web service + free PostgreSQL).
  - Production `Dockerfile` and dynamic `$PORT` handling.
- **Developer Experience**:
  - `docker-compose.yml` for local FastAPI + PostgreSQL 16 + Weaviate.
  - Automated test suite with `pytest` and `pytest-asyncio`.

---

## 📁 Project Structure

```
.
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── auth.py          # /register, /login, /login/oauth, /me
│   │       │   ├── health.py        # /health (liveness) & /ready (DB/Weaviate probes)
│   │       │   ├── users.py         # Profile updates & admin user listings
│   │       │   └── vectors.py       # Document chunk ingestion & hybrid vector search
│   │       └── router.py            # API v1 router
│   ├── core/
│   │   ├── config.py                # Pydantic Settings (.env, Render URL conversion)
│   │   ├── deps.py                  # Auth & DB dependency injection
│   │   └── security.py              # Password hashing & JWT token encode/decode
│   ├── db/
│   │   ├── base.py                  # DeclarativeBase & TimestampMixin
│   │   └── session.py               # Async SQLAlchemy engine & sessionmaker
│   ├── models/
│   │   └── user.py                  # User SQL model (UUID, email, password, roles)
│   ├── schemas/
│   │   ├── token.py                 # JWT Token models
│   │   ├── user.py                  # User create/read/update schemas
│   │   └── vector.py                # Document chunk & search schemas
│   ├── vector/
│   │   └── weaviate_client.py       # Weaviate v4 client lifecycle & search manager
│   └── main.py                      # FastAPI lifespan, CORS, and startup
├── alembic/                         # Database migration scripts
│   ├── versions/
│   │   └── 0001_initial_users.py    # Users table creation
│   └── env.py                       # Async migration runner
├── tests/
│   ├── conftest.py                  # Pytest async fixtures & isolated in-memory DB
│   ├── test_auth.py                 # Auth & registration tests
│   ├── test_health.py               # Liveness & readiness tests
│   └── test_vectors.py              # Vector schema & status tests
├── .env.example                     # Environment variables template
├── alembic.ini                      # Alembic configuration
├── docker-compose.yml               # Local stack (FastAPI + Postgres + Weaviate)
├── Dockerfile                       # Production multi-stage Docker build
├── render.yaml                      # Render 1-click Blueprint
└── requirements.txt                 # Pinned dependencies
```

---

## 🚀 Quickstart (Local Development)

### Method 1: Local Python Virtual Environment

1. **Clone the repository and enter the directory**:
   ```bash
   cd legal-ai-backend
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```

5. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```

6. **Start the local development server**:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

7. **Explore the APIs**:
   - Interactive Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
   - ReDoc documentation: [http://localhost:8000/redoc](http://localhost:8000/redoc)
   - Liveness Probe: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
   - Readiness Probe: [http://localhost:8000/api/v1/ready](http://localhost:8000/api/v1/ready)

---

### Method 2: One-Command Local Docker Compose

Spin up the entire stack—**FastAPI with hot reload**, **PostgreSQL 16**, and **Weaviate v1.27**—with a single command:

```bash
docker compose up --build
```

- **Backend API**: `http://localhost:8000`
- **PostgreSQL**: `localhost:5432` (`postgres:postgres`)
- **Weaviate REST**: `http://localhost:8080`
- **Weaviate gRPC**: `localhost:50051`

---

## 🌐 Deploying Freely to Render.com

Render offers a free tier for Web Services and PostgreSQL. This repository includes a pre-configured `render.yaml` Blueprint.

### Option A: Render 1-Click Blueprint (Recommended)

1. Push your repository to **GitHub** or **GitLab**.
2. Log in to [Render.com](https://dashboard.render.com/).
3. Click **New +** -> **Blueprint**.
4. Connect your repository.
5. Render reads `render.yaml` and will automatically configure:
   - A **Web Service** running your FastAPI app.
   - A **Free PostgreSQL Database** linked via `DATABASE_URL`.
   - Automatic execution of `alembic upgrade head` before booting `uvicorn`.
6. Click **Apply**.

### Option B: Manual Web Service Setup on Render

1. On the Render dashboard, click **New +** -> **Web Service**.
2. Select your repository.
3. Configure the settings:
   - **Runtime**: `Python`
   - **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command**: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: `Free`
4. In **Environment Variables**, set:
   - `ENVIRONMENT` = `production`
   - `JWT_SECRET_KEY` = *(click Generate)*
   - `DATABASE_URL` = *(Your Render or external PostgreSQL connection string)*
   - `WEAVIATE_URL` = *(Your Weaviate Cloud cluster URL)*
   - `WEAVIATE_API_KEY` = *(Your Weaviate API key)*
   - `CORS_ORIGINS` = `*` (or your frontend domain)

> [!NOTE]
> **Render Postgres URL Compatibility**: Render provides connection strings starting with `postgres://`. The backend automatically converts this to `postgresql+asyncpg://` at runtime.

---

## 🧠 Connecting Weaviate Cloud (Free Sandbox)

For vector search on Render's free tier, use a free cluster from **Weaviate Cloud (WCS)**:

1. Create a free account at [console.weaviate.cloud](https://console.weaviate.cloud/).
2. Create a free sandbox cluster (14-day renewable free sandbox).
3. Copy your **REST endpoint URL** and **API key**.
4. In your `.env` (or Render environment variables), set:
   ```env
   WEAVIATE_URL=https://your-cluster-name.weaviate.network
   WEAVIATE_API_KEY=your_cluster_api_key_here
   ```
5. Check `http://localhost:8000/api/v1/vectors/status` to verify active connection.

---

## 🛠️ Database Migrations with Alembic

- **Run all pending migrations**:
  ```bash
  alembic upgrade head
  ```

- **Create a new migration after modifying models in `app/models/`**:
  ```bash
  alembic revision --autogenerate -m "Add new field to user"
  ```

- **Roll back the last migration**:
  ```bash
  alembic downgrade -1
  ```

---

## 🧪 Running Automated Tests

Run the test suite using `pytest`:

```bash
pytest -v
```

The test suite runs against an isolated async in-memory database without requiring a live PostgreSQL or Weaviate instance.
