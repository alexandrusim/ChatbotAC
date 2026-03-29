import os
import shutil
from fastapi import FastAPI, HTTPException, File, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse 
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import engine, get_db, SessionLocal
import models
from router import rule_based_router
from rag_engine import get_ai_response, reindex_ai_knowledge, build_rag_chain

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


# EVENIMENT DE PORNIRE (STARTUP)
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
    
    print("Initializez sistemul AI...")
    build_rag_chain()


# MODELE PYDANTIC (Pentru validarea datelor primite) 
class ChatRequest(BaseModel):
    message: str

class RuleRequest(BaseModel):
    keyword: str
    response: str

class LinkRequest(BaseModel):
    path: str
    
class FeedbackRequest(BaseModel):
    rating: int

# ENDPOINT-URI PENTRU CHAT PUBLIC

@app.get("/")
def read_root():
    return {"status": "Sistemul hibrid este online!"}

@app.get("/chat-ui")
def serve_frontend():
    return FileResponse("frontend/index.html")

@app.post("/chat")
async def chat_endpoint(request: ChatRequest, db: Session = Depends(get_db)):
    user_message = request.message
    
    if not user_message.strip():
        raise HTTPException(status_code=400, detail="Mesajul nu poate fi gol.")
    
    # 1. Rutare Rule-Based
    rule_response = rule_based_router(user_message, db)
    if rule_response:
        log = models.Conversation(user_message=user_message, bot_response=rule_response, source="rule-based")
        db.add(log)
        db.commit()
        db.refresh(log) 
        return {"answer": rule_response, "source": "rule-based", "conversation_id": log.id} 
    
    # 2. Rutare Inteligenta Artificiala (RAG)
    try:
        ai_answer = get_ai_response(user_message)
        log = models.Conversation(user_message=user_message, bot_response=ai_answer, source="ai-rag")
        db.add(log)
        db.commit()
        db.refresh(log) 
        return {"answer": ai_answer, "source": "ai-rag", "conversation_id": log.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ENDPOINT-URI PENTRU DASHBOARD (ADMIN)

@app.get("/dashboard")
def serve_dashboard():
    return FileResponse("frontend/dashboard.html")

@app.get("/logs")
def get_logs(db: Session = Depends(get_db)):
    # ultimele 50 conversatii in ordine descrescatoare
    conversations = db.query(models.Conversation).order_by(models.Conversation.id.desc()).limit(50).all()
    history = [
        {
            "data": c.timestamp, 
            "intrebare_utilizator": c.user_message, 
            "raspuns_bot": c.bot_response, 
            "sursa": c.source,
            "rating": c.rating
        } for c in conversations
    ]
    return {"istoric_conversatii": history}

# REGULI FIXE 
@app.get("/api/rules")
def get_rules(db: Session = Depends(get_db)):
    rules = db.query(models.Rule).all()
    return [{"id": r.id, "keyword": r.keyword, "response": r.response} for r in rules]

@app.post("/api/rules")
def add_rule(rule: RuleRequest, db: Session = Depends(get_db)):
    try:
        new_rule = models.Rule(keyword=rule.keyword.lower(), response=rule.response)
        db.add(new_rule)
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Cuvantul cheie exista deja sau eroare de baza de date.")

@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(models.Rule).filter(models.Rule.id == rule_id).first()
    if rule:
        db.delete(rule)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Regula nu a fost gasita.")

# SURSE WEB (LINK-URI)
@app.get("/api/weblinks")
def get_weblinks(db: Session = Depends(get_db)):
    links = db.query(models.Weblink).all()
    return [{"id": l.id, "type": l.type, "path": l.path} for l in links]

@app.post("/api/weblinks")
def add_weblink(link: LinkRequest, db: Session = Depends(get_db)):
    try:
        new_link = models.Weblink(path=link.path)
        db.add(new_link)
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Link-ul exista deja sau eroare de baza de date.")

@app.delete("/api/weblinks/{link_id}")
def delete_weblink(link_id: int, db: Session = Depends(get_db)):
    link = db.query(models.Weblink).filter(models.Weblink.id == link_id).first()
    if link:
        db.delete(link)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Link-ul nu a fost gasit.")

# RE-INDEXARE AI 
@app.post("/api/reindex")
def reindex_ai():
    try:
        reindex_ai_knowledge()
        return {"status": "Re-indexare completata cu succes! AI-ul are acum cunostintele actualizate."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# GESTIUNE DOCUMENTE PDF 
@app.get("/api/documents")
def get_documents():
    if not os.path.exists("date"):
        return []
    files = [f for f in os.listdir("date") if f.lower().endswith(".pdf")]
    return [{"filename": f} for f in files]

@app.post("/api/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Doar fisierele PDF sunt permise.")
    
    if not os.path.exists("date"):
        os.makedirs("date")

    file_path = os.path.join("date", file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"status": "success", "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/documents/{filename}")
def delete_document(filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nume de fisier invalid.")
    
    file_path = os.path.join("date", filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return {"status": "success"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Fisierul nu a fost gasit.")


# SISTEM DE FEEDBACK 
@app.post("/feedback/{conversation_id}")
def submit_feedback(conversation_id: int, feedback: FeedbackRequest, db: Session = Depends(get_db)):
    conv = db.query(models.Conversation).filter(models.Conversation.id == conversation_id).first()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversatia nu a fost gasita.")
        
    conv.rating = feedback.rating
    db.commit()
    
    return {"message": "Feedback salvat cu succes!", "rating": feedback.rating}