from sqlalchemy import Column, Integer, String, Text
from datetime import datetime
from database import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String(50), default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    user_message = Column(Text)  # Folosim Text pentru mesaje lungi
    bot_response = Column(Text)
    source = Column(String(50))

class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(100), unique=True, index=True)
    response = Column(Text)

class Weblink(Base):
    __tablename__ = "weblinks"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(50), default="url")
    path = Column(String(500), unique=True, index=True)