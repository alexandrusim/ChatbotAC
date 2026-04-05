import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import engine, SessionLocal
import models
from rag_engine import reindex_ai_knowledge
from router import router

os.environ["USER_AGENT"] = "TUIASI-Chatbot/1.0"

# CONFIGURARE FASTAPI 
app = FastAPI(title="Admitere Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# RUTARE FISIERE STATICE (CSS/JS) 
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# STARTUP
@app.on_event("startup")
def startup_event():
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    if db.query(models.Rule).count() == 0:
        default_rules = [
            ("contact", "Ne poti contacta la numarul de telefon 0232 278 683 sau prin email la secretariat@ac.tuiasi.ro."),
            ("telefon", "Numarul de telefon al secretariatului AC este 0232 278 683."),
            ("adresa", "Facultatea de Automatica si Calculatoare se afla pe Bulevardul Profesor Dimitrie Mangeron 27, Iasi."),
            ("locatie", "Facultatea se afla pe Bd. Dimitrie Mangeron nr. 27, Iasi."),
            ("program", "Programul secretariatului pentru public este de regula de Luni pana Vineri, in intervalul orar 09:00 - 13:00.")
        ]
        for kw, resp in default_rules:
            db.add(models.Rule(keyword=kw, response=resp))
        
    if db.query(models.Weblink).count() == 0:
        default_urls = [
            ("url", "https://ac.tuiasi.ro/admitere/licenta/"),
            ("url", "https://ac.tuiasi.ro/admitere/masterat/"),
            ("url", "https://www.admitere.tuiasi.ro/licenta/index.php"),
            ("url", "https://www.tuiasi.ro/licenta/")
        ]
        for t, p in default_urls:
            db.add(models.Weblink(type=t, path=p))
            
    db.commit()
    db.close()
    
    print("Initializez memoria AI...")
    reindex_ai_knowledge()

app.include_router(router)