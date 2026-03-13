import asyncio
import json
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional, List

import asyncpg
import aioredis
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from jose import jwt

# ------------------ Config ------------------
class Settings:
    DB_USER = "postgres"
    DB_PASSWORD = "postgres"
    DB_NAME = "postgres"
    DB_HOST = "db"
    DB_PORT = "5432"
    REDIS_HOST = "redis"
    REDIS_PORT = 6379
    JWT_SECRET = "supersecret"
    JWT_ALGORITHM = "HS256"

settings = Settings()

# ------------------ Database ------------------
class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            min_size=1,
            max_size=10,
        )
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    title VARCHAR(255) NOT NULL,
                    text TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            ''')

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def fetch(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def execute(self, query, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

db = Database()

# ------------------ Redis ------------------
class RedisClient:
    def __init__(self):
        self.client = None

    async def connect(self):
        self.client = aioredis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
            encoding="utf-8",
            decode_responses=True
        )

    async def disconnect(self):
        if self.client:
            await self.client.close()

    async def get(self, key):
        return await self.client.get(key)

    async def setex(self, key, ttl, value):
        await self.client.setex(key, ttl, value)

    async def delete(self, key):
        await self.client.delete(key)

redis_client = RedisClient()

# ------------------ Auth ------------------
def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return int(payload.get("sub"))
    except jwt.JWTError:
        return None

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    user = await db.fetchrow("SELECT id, name FROM users WHERE id = $1", user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return dict(user)

# ------------------ Schemas ------------------
class UserCreate(BaseModel):
    name: str

class UserResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime

class UserUpdate(BaseModel):
    name: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PostCreate(BaseModel):
    title: str = Field(..., max_length=255)
    text: str

class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    text: Optional[str] = None

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

# ------------------ Users API ------------------
@app.post("/users", response_model=TokenResponse)
async def create_user(user: UserCreate):
    now = datetime.utcnow()
    row = await db.fetchrow(
        "INSERT INTO users (name, created_at, updated_at) VALUES ($1, $2, $2) RETURNING id",
        user.name, now
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
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

@app.patch("/users/me", response_model=UserResponse)
async def update_user(user_update: UserUpdate, current_user: dict = Depends(get_current_user)):
    await db.execute(
        "UPDATE users SET name = $1, updated_at = $2 WHERE id = $3",
        user_update.name, datetime.utcnow(), current_user["id"]
    )
    updated = await db.fetchrow("SELECT id, name, created_at, updated_at FROM users WHERE id = $1", current_user["id"])
    return dict(updated)

@app.delete("/users/me", status_code=204)
async def delete_user(current_user: dict = Depends(get_current_user)):
    await db.execute("DELETE FROM users WHERE id = $1", current_user["id"])
    return None

# ------------------ Posts API ------------------
POST_CACHE_TTL = 600  # 10 минут

async def get_post_from_db(post_id: int):
    await asyncio.sleep(2)  # симуляция нагрузки
    row = await db.fetchrow(
        "SELECT id, user_id, title, text, created_at, updated_at FROM posts WHERE id = $1",
        post_id
    )
    return dict(row) if row else None

@app.post("/posts", response_model=PostResponse)
async def create_post(post: PostCreate, current_user: dict = Depends(get_current_user)):
    now = datetime.utcnow()
    row = await db.fetchrow(
        "INSERT INTO posts (user_id, title, text, created_at, updated_at) VALUES ($1, $2, $3, $4, $4) RETURNING id, user_id, title, text, created_at, updated_at",
        current_user["id"], post.title, post.text, now
    )
    new_post = dict(row)
    # Всегда кэшируем новый пост (он горячий)
    await redis_client.setex(f"post:{new_post['id']}", POST_CACHE_TTL, json.dumps(new_post, default=str))
    return new_post

@app.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(post_id: int):
    # Проверяем кэш
    cached = await redis_client.get(f"post:{post_id}")
    if cached:
        post = json.loads(cached)
        created_at = datetime.fromisoformat(post["created_at"])
        # Если пост горячий (менее 10 минут), отдаём из кэша
        if created_at >= datetime.utcnow() - timedelta(minutes=10):
            return post
        else:
            # Пост устарел, удаляем из кэша
            await redis_client.delete(f"post:{post_id}")

    # Иначе идём в БД
    post = await get_post_from_db(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Если пост горячий, кэшируем
    if post["created_at"] >= datetime.utcnow() - timedelta(minutes=10):
        await redis_client.setex(f"post:{post_id}", POST_CACHE_TTL, json.dumps(post, default=str))
    return post

@app.patch("/posts/{post_id}", response_model=PostResponse)
async def update_post(post_id: int, post_update: PostUpdate, current_user: dict = Depends(get_current_user)):
    existing = await db.fetchrow("SELECT user_id FROM posts WHERE id = $1", post_id)
    if not existing or existing["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    fields = []
    values = []
    idx = 1
    if post_update.title is not None:
        fields.append(f"title = ${idx}")
        values.append(post_update.title)
        idx += 1
    if post_update.text is not None:
        fields.append(f"text = ${idx}")
        values.append(post_update.text)
        idx += 1
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    fields.append(f"updated_at = ${idx}")
    values.append(datetime.utcnow())
    idx += 1
    values.append(post_id)
    query = f"UPDATE posts SET {', '.join(fields)} WHERE id = ${idx} RETURNING id, user_id, title, text, created_at, updated_at"
    row = await db.fetchrow(query, *values)
    updated = dict(row)
    # Инвалидируем кэш
    await redis_client.delete(f"post:{post_id}")
    # Если пост всё ещё горячий, кэшируем обновлённый
    if updated['created_at'] >= datetime.utcnow() - timedelta(minutes=10):
        await redis_client.setex(f"post:{post_id}", POST_CACHE_TTL, json.dumps(updated, default=str))
    return updated

@app.delete("/posts/{post_id}", status_code=204)
async def delete_post(post_id: int, current_user: dict = Depends(get_current_user)):
    existing = await db.fetchrow("SELECT user_id FROM posts WHERE id = $1", post_id)
    if not existing or existing["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.execute("DELETE FROM posts WHERE id = $1", post_id)
    await redis_client.delete(f"post:{post_id}")
    return None

@app.get("/users/me/posts", response_model=List[PostResponse])
async def get_my_posts(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    await asyncio.sleep(2)  # симуляция нагрузки
    rows = await db.fetch(
        "SELECT id, user_id, title, text, created_at, updated_at FROM posts WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
        current_user["id"], limit, offset
    )
    return [dict(r) for r in rows]
