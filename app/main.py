import os
import datetime
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

from app import models
from app.outline_api import OutlineServer
from sqlalchemy.future import select

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGO = os.getenv("JWT_ALGORITHM")
JWT_EXP_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
SERVER_CONFIG = {k.replace("SERVER_", ""): v for k, v in os.environ.items() if k.startswith("SERVER_")}

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
models.Base.metadata.create_all(bind=engine.sync_engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI()

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def create_jwt(user_id: int):
    expire = datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXP_HOURS)
    data = {"sub": str(user_id), "exp": expire}
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGO)

@app.post("/register", response_model=Token)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == user.email))
    if result.scalar():
        raise HTTPException(status_code=400, detail="User already exists")
    hashed = pwd_context.hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    token = create_jwt(db_user.id)
    return {"access_token": token}

@app.post("/login", response_model=Token)
async def login(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(models.User).where(models.User.email == user.email))
    db_user = result.scalar()
    if not db_user or not pwd_context.verify(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_jwt(db_user.id)
    return {"access_token": token}

@app.post("/get-key")
async def get_key(current_user_id: int = 1, db: AsyncSession = Depends(get_db)):
    server_id, access_url = sorted(SERVER_CONFIG.items(), key=lambda x: x[0])[0]  # заглушка
    outline = OutlineServer(access_url)
    key = await outline.create_key(f"user-{current_user_id}")

    expires = datetime.datetime.utcnow() + datetime.timedelta(days=30)
    subscription = models.Subscription(
        user_id=current_user_id,
        server_id=server_id,
        outline_key_id=key["id"],
        access_url=key["accessUrl"],
        expires_at=expires
    )
    db.add(subscription)
    await db.commit()
    return {"accessUrl": key["accessUrl"]}