from sqlalchemy.orm import Session
from models import Rule

def rule_based_router(message: str, db: Session):
    msg_lower = message.lower().strip()
    
    if len(msg_lower) > 60:
        return None
        
    greetings = ["salut", "buna", "hey", "hello", "seara", "ziua", "dimineata"]
    if any(greet in msg_lower for greet in greetings) and len(msg_lower) < 25:
        return "Salut! Sunt asistentul virtual pentru admiterea la TUIASI. Cu ce te pot ajuta astazi?"
        
    thanks = ["mersi", "ms", "multumesc", "multam"]
    if any(thx in msg_lower for thx in thanks) and len(msg_lower) < 25:
        return "Cu multa placere! Mult succes la admitere! Daca mai ai intrebari, sunt aici."

    rules = db.query(Rule).all()
    
    for r in rules:
        if r.keyword in msg_lower:
            return r.response
            
    return None