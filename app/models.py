from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    subscriptions = relationship('Subscription', back_populates='user')

class Subscription(Base):
    __tablename__ = 'subscriptions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    server_id = Column(String, nullable=False)
    outline_key_id = Column(String, nullable=False)
    access_url = Column(String, nullable=False)
    plan = Column(Integer, default=0)  # уровень подписки
    last_login = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)

    user = relationship('User', back_populates='subscriptions')