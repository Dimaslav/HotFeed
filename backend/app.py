import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg
import redis.asyncio as redis
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ------------------ Config ------------------
class Settings(BaseSettings):
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "postgres"
    DB_HOST: str = "db"
    DB_PORT: int = 5432

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    JWT_SECRET: str = "supersecret"
    JWT_ALGORITHM: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


# ------------------ Helpers ------------------
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize_json_value(value: Any):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Type {type(value)!r} is not JSON serializable")


def dump_json(data: Any) -> str:
    return json.dumps(data, default=serialize_json_value, ensure_ascii=False)


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, str):
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    raise TypeError(f"Unsupported datetime value: {value!r}")


def normalize_post(data: dict[str, Any]) -> dict[str, Any]:
    post = dict(data)
    post["id"] = int(post["id"])
    post["user_id"] = int(post["user_id"])
    post["created_at"] = parse_datetime(post["created_at"])
    post["updated_at"] = parse_datetime(post["updated_at"])
    return post


def is_auth_error(message: str) -> bool:
    message = message or ""
    return any(
        keyword.lower() in message.lower()
        for keyword in ["not authenticated", "invalid token", "user not found"]
    )


# ------------------ Database ------------------
class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            min_size=1,
            max_size=10,
            command_timeout=30,
        )

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title VARCHAR(255) NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_posts_user_created_at
                ON posts (user_id, created_at DESC)
                """
            )

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def fetch(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)


db = Database()


# ------------------ Redis ------------------
class RedisClient:
    def __init__(self):
        self.client: redis.Redis | None = None

    async def connect(self):
        self.client = redis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
            encoding="utf-8",
            decode_responses=True,
        )

    async def disconnect(self):
        if self.client:
            await self.client.aclose()

    async def get(self, key: str):
        return await self.client.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        await self.client.setex(key, ttl, value)

    async def delete(self, *keys: str):
        if not keys:
            return 0
        return await self.client.delete(*keys)


redis_client = RedisClient()


# ------------------ Auth ------------------
def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": utcnow() + timedelta(days=30),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (JWTError, ValueError, TypeError):
        return None


security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user = await db.fetchrow(
        "SELECT id, name, created_at, updated_at FROM users WHERE id = $1",
        user_id,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return dict(user)


# ------------------ Schemas ------------------
class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class UserUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class UserResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    text: str = Field(..., min_length=1)


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    text: Optional[str] = Field(None, min_length=1)


class PostResponse(BaseModel):
    id: int
    user_id: int
    title: str
    text: str
    created_at: datetime
    updated_at: datetime


# ------------------ Lifespan ------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    await redis_client.connect()
    yield
    await db.disconnect()
    await redis_client.disconnect()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


POST_CACHE_TTL = 600  # 10 минут


async def get_post_from_db(post_id: int) -> Optional[dict[str, Any]]:
    row = await db.fetchrow(
        "SELECT id, user_id, title, text, created_at, updated_at FROM posts WHERE id = $1",
        post_id,
    )
    return normalize_post(dict(row)) if row else None


# ------------------ Users API ------------------
@app.post("/users", response_model=TokenResponse)
async def create_user(user: UserCreate):
    name = user.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    now = utcnow()
    row = await db.fetchrow(
        """
        INSERT INTO users (name, created_at, updated_at)
        VALUES ($1, $2, $2)
        RETURNING id
        """,
        name,
        now,
    )
    token = create_access_token(row["id"])
    return {"access_token": token}


@app.get("/users/{user_id}/token", response_model=TokenResponse)
async def get_token(user_id: int):
    user = await db.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_access_token(user_id)
    return {"access_token": token}


@app.get("/users/me", response_model=UserResponse)
async def get_me(current_user: dict[str, Any] = Depends(get_current_user)):
    return current_user


@app.patch("/users/me", response_model=UserResponse)
async def update_user(
    user_update: UserUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    name = user_update.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    now = utcnow()
    await db.execute(
        "UPDATE users SET name = $1, updated_at = $2 WHERE id = $3",
        name,
        now,
        current_user["id"],
    )
    updated = await db.fetchrow(
        "SELECT id, name, created_at, updated_at FROM users WHERE id = $1",
        current_user["id"],
    )
    return dict(updated)


@app.delete("/users/me", status_code=204)
async def delete_user(current_user: dict[str, Any] = Depends(get_current_user)):
    posts = await db.fetch(
        "SELECT id FROM posts WHERE user_id = $1",
        current_user["id"],
    )
    post_keys = [f"post:{row['id']}" for row in posts]

    await db.execute("DELETE FROM users WHERE id = $1", current_user["id"])

    if post_keys:
        await redis_client.delete(*post_keys)

    return None


# ------------------ Posts API ------------------
@app.post("/posts", response_model=PostResponse)
async def create_post(
    post: PostCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    title = post.title.strip()
    text = post.text.strip()

    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    now = utcnow()
    row = await db.fetchrow(
        """
        INSERT INTO posts (user_id, title, text, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $4)
        RETURNING id, user_id, title, text, created_at, updated_at
        """,
        current_user["id"],
        title,
        text,
        now,
    )

    new_post = normalize_post(dict(row))
    await redis_client.setex(
        f"post:{new_post['id']}",
        POST_CACHE_TTL,
        dump_json(new_post),
    )
    return new_post


@app.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(post_id: int):
    cache_key = f"post:{post_id}"
    cached = await redis_client.get(cache_key)

    if cached:
        try:
          post = normalize_post(json.loads(cached))
          if post["created_at"] >= utcnow() - timedelta(minutes=10):
              return post
          await redis_client.delete(cache_key)
        except (json.JSONDecodeError, ValueError, TypeError):
            await redis_client.delete(cache_key)

    post = await get_post_from_db(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post["created_at"] >= utcnow() - timedelta(minutes=10):
        await redis_client.setex(cache_key, POST_CACHE_TTL, dump_json(post))

    return post


@app.patch("/posts/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: int,
    post_update: PostUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    existing = await db.fetchrow("SELECT user_id FROM posts WHERE id = $1", post_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")
    if existing["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")

    fields: list[str] = []
    values: list[Any] = []
    idx = 1

    if post_update.title is not None:
        title = post_update.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        fields.append(f"title = ${idx}")
        values.append(title)
        idx += 1

    if post_update.text is not None:
        text = post_update.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        fields.append(f"text = ${idx}")
        values.append(text)
        idx += 1

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    now = utcnow()
    fields.append(f"updated_at = ${idx}")
    values.append(now)
    idx += 1

    values.append(post_id)
    query = f"""
        UPDATE posts
        SET {", ".join(fields)}
        WHERE id = ${idx}
        RETURNING id, user_id, title, text, created_at, updated_at
    """

    row = await db.fetchrow(query, *values)
    updated = normalize_post(dict(row))

    cache_key = f"post:{post_id}"
    await redis_client.delete(cache_key)

    if updated["created_at"] >= utcnow() - timedelta(minutes=10):
        await redis_client.setex(cache_key, POST_CACHE_TTL, dump_json(updated))

    return updated


@app.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    existing = await db.fetchrow("SELECT user_id FROM posts WHERE id = $1", post_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")
    if existing["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute("DELETE FROM posts WHERE id = $1", post_id)
    await redis_client.delete(f"post:{post_id}")
    return None


@app.get("/users/me/posts", response_model=list[PostResponse])
async def get_my_posts(
    current_user: dict[str, Any] = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows = await db.fetch(
        """
        SELECT id, user_id, title, text, created_at, updated_at
        FROM posts
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        current_user["id"],
        limit,
        offset,
    )
    return [normalize_post(dict(row)) for row in rows]
