import spacy
from sqlalchemy.orm import Session
from models import Rule

print("Se incarca modelul NLP spaCy pentru limba romana...")
nlp = spacy.load("ro_core_news_sm")

def rule_based_router(message: str, db: Session):
    msg_lower = message.lower().strip()
    
    if len(msg_lower) > 60:
        return None
        
    cuvinte = msg_lower.split()
        
    greetings = ["salut", "sal", "buna", "hey", "hello", "seara", "ziua", "dimineata", "neata", "hei", "hi"]
    
    if any(greet in msg_lower for greet in greetings) and len(cuvinte) <= 3:
        return "Salut! Sunt asistentul virtual pentru admiterea la TUIASI. Cu ce te pot ajuta astazi?"
        
    thanks = ["mersi", "ms", "multumesc", "multam"]
    if any(thx in msg_lower for thx in thanks) and len(cuvinte) <= 3:
        return "Cu multa placere! Mult succes la admitere! Daca mai ai intrebari, sunt aici."

    doc = nlp(message)
    
    clean_words = [token.text.lower() for token in doc if not token.is_punct]
    lemmas = [token.lemma_.lower() for token in doc if not token.is_punct]
    
    personal_pronouns = ["eu", "meu", "mea", "mei", "mele", "mie", "mi", "ma", "lui", "ei", "lor"]
    
    has_personal_context = any(pronoun in clean_words for pronoun in personal_pronouns)

    cuvinte_interogative = ["care", "ce", "cine", "unde", "cum", "cand"]
    has_proper_noun = any(token.pos_ == "PROPN" and token.text.lower() not in cuvinte_interogative for token in doc)

    rules = db.query(Rule).all()
    
    for r in rules:
        keyword = r.keyword.lower()
        
        if keyword in lemmas or keyword in msg_lower:
            
            if (has_personal_context or has_proper_noun) and keyword in ["telefon", "numar", "adresa", "dosar", "acte"]:
                print(f"[NLP Router] Context personal/nume propriu detectat pentru '{keyword}'. Trimit catre AI.")
                return None 
                
            print(f"[NLP Router] Regula declansata pentru: {keyword}")
            return r.response
            
    return None