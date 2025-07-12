import os
import time
import datetime
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, EmailStr
from jose import jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

from app import models
from app.outline_api import OutlineServer

load_dotenv()

# Конфигурация
DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGO = os.getenv("JWT_ALGORITHM")
JWT_EXP_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
SERVER_CONFIG = {k.replace("SERVER_", ""): v for k,v in os.environ.items() if k.startswith("SERVER_")}

# DB setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
models.Base.metadata.create_all(bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI()

# Pydantic models
template:
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class SubscriptionInfo(BaseModel):
    access_url: str
    plan: int
    expires_at: datetime.datetime

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# JWT
def create_jwt(user_id: int):
    exp = datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXP_HOURS)
    return jwt.encode({"sub":str(user_id),"exp":exp}, JWT_SECRET, algorithm=JWT_ALGO)

# Register endpoint
@app.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter_by(email=user.email).first():
        raise HTTPException(400, "User already exists")
    user_hashed = pwd_context.hash(user.password)
    db_user = models.User(email=user.email, hashed_password=user_hashed)
    db.add(db_user); db.commit(); db.refresh(db_user)
    # Outline key: plan 0 (1GB), expiry 10 years
    sid, url = sorted(SERVER_CONFIG.items())[0]
    outline = OutlineServer(url)
    key = outline.create_key(name=f"user-{db_user.id}", data_limit=1_000_000_000)
    expiry = datetime.datetime.utcnow() + datetime.timedelta(days=3650)
    sub = models.Subscription(
        user_id=db_user.id, server_id=sid,
        outline_key_id=key['id'], access_url=key['accessUrl'],
        plan=0, last_login=None, expires_at=expiry
    )
    db.add(sub); db.commit()
    return {"access_token": create_jwt(db_user.id)}

# Login endpoint
@app.post("/login", response_model=SubscriptionInfo)
def login(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter_by(email=user.email).first()
    if not db_user or not pwd_context.verify(user.password, db_user.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    sub = db.query(models.Subscription).filter_by(user_id=db_user.id).order_by(models.Subscription.id.desc()).first()
    sub.last_login = datetime.datetime.utcnow()
    db.commit()
    return SubscriptionInfo(access_url=sub.access_url, plan=sub.plan, expires_at=sub.expires_at)

# Upgrade subscription
@app.post("/upgrade")
def upgrade(current_user_id: int, db: Session = Depends(get_db)):
    sub = db.query(models.Subscription).filter_by(user_id=current_user_id).order_by(models.Subscription.id.desc()).first()
    if sub.plan >= 1:
        raise HTTPException(400, "Already upgraded")
    outline = OutlineServer(SERVER_CONFIG[sub.server_id])
    outline.delete_key(sub.outline_key_id)
    key = outline.create_key(name=f"user-{current_user_id}")
    sub.outline_key_id, sub.access_url, sub.plan = key['id'], key['accessUrl'], 1
    sub.expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
    db.commit()
    return {"access_url": sub.access_url, "plan": sub.plan, "expires_at": sub.expires_at}

# Cleanup task
def cleanup_task():
    while True:
        db = SessionLocal(); now=datetime.datetime.utcnow()
        for sub in db.query(models.Subscription).all():
            outline = OutlineServer(SERVER_CONFIG[sub.server_id])
            if sub.expires_at < now:
                outline.delete_key(sub.outline_key_id)
                key = outline.create_key(name=f"user-{sub.user_id}", data_limit=1_000_000_000)
                sub.outline_key_id, sub.access_url, sub.plan, sub.expires_at = (
                    key['id'], key['accessUrl'], 0, now+datetime.timedelta(days=3650)
                )
            if sub.last_login and (now-sub.last_login).days > 180:
                outline.delete_key(sub.outline_key_id)
                db.delete(sub); db.delete(db.query(models.User).get(sub.user_id))
        db.commit(); db.close(); time.sleep(86400)

@app.on_event("startup")
def start_cleanup():
    import threading
    threading.Thread(target=cleanup_task, daemon=True).start()