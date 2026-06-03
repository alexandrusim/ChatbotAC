import os
import shutil
import jwt
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, File, UploadFile, Depends, status
from fastapi.responses import FileResponse 
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
import models
from rule_based import rule_based_router
from rag_engine import get_ai_response, reindex_ai_knowledge

router = APIRouter()

# --- CONFIGURARE JWT (SECURITATE) ---
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("EROARE CRITICA: JWT_SECRET_KEY lipseste din fisierul .env!")

ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120 # Tokenul expira in 2 ore

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_admin(token: str = Depends(oauth2_scheme)):
    """Functie care verifica daca user-ul are un token valid pentru a accesa API-urile de admin."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Token invalid")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirat! Te rog sa te reloghezi.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Nu ai acces!")

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username == ADMIN_USER and form_data.password == ADMIN_PASS:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode = {"sub": form_data.username, "exp": expire}
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": encoded_jwt, "token_type": "bearer"}
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Utilizator sau parolă incorecte",
        headers={"WWW-Authenticate": "Bearer"},
    )
# ------------------------------------

# MODELE PYDANTIC
class ChatRequest(BaseModel):
    message: str

class RuleRequest(BaseModel):
    keyword: str
    response: str

class LinkRequest(BaseModel):
    path: str
    
class FeedbackRequest(BaseModel):
    rating: int

class TextRequest(BaseModel):
    content: str

# =====================================================================
# ENDPOINT-URI PENTRU CHAT PUBLIC (Accesibile de catre oricine)
# =====================================================================

@router.get("/")
def read_root():
    return {"status": "Sistemul hibrid este online!"}

@router.get("/chat-ui")
def serve_frontend():
    return FileResponse("frontend/index.html")

@router.post("/chat")
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
        ai_answer, nume_model = get_ai_response(user_message)
        sursa_exacta = f"ai-rag ({nume_model})"
        log = models.Conversation(user_message=user_message, bot_response=ai_answer, source=sursa_exacta)
        
        db.add(log)
        db.commit()
        db.refresh(log) 
        
        return {"answer": ai_answer, "source": sursa_exacta, "conversation_id": log.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/feedback/{conversation_id}")
def submit_feedback(conversation_id: int, feedback: FeedbackRequest, db: Session = Depends(get_db)):
    conv = db.query(models.Conversation).filter(models.Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversatia nu a fost gasita.")
        
    conv.rating = feedback.rating
    db.commit()
    return {"message": "Feedback salvat cu succes!", "rating": feedback.rating}


# =====================================================================
# ENDPOINT-URI PENTRU DASHBOARD (PROTEJATE DE JWT)
# =====================================================================

@router.get("/dashboard")
def serve_dashboard():
    return FileResponse("frontend/dashboard.html")

@router.get("/logs")
def get_logs(db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
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

# ==========================================
# GESTIUNE REGULI FIXE
# ==========================================
@router.get("/api/rules")
def get_rules(db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    rules = db.query(models.Rule).all()
    return [{"id": r.id, "keyword": r.keyword, "response": r.response} for r in rules]

@router.post("/api/rules")
def add_rule(rule: RuleRequest, db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    try:
        new_rule = models.Rule(keyword=rule.keyword.lower(), response=rule.response)
        db.add(new_rule)
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Cuvantul cheie exista deja sau eroare de baza de date.")

@router.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    rule = db.query(models.Rule).filter(models.Rule.id == rule_id).first()
    if rule:
        db.delete(rule)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Regula nu a fost gasita.")

# ==========================================
# GESTIUNE SURSE WEB (LINK-URI)
# ==========================================
@router.get("/api/weblinks")
def get_weblinks(db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    links = db.query(models.Weblink).all()
    return [{"id": l.id, "type": l.type, "path": l.path} for l in links]

@router.post("/api/weblinks")
def add_weblink(link: LinkRequest, db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    try:
        new_link = models.Weblink(path=link.path)
        db.add(new_link)
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Link-ul exista deja sau eroare de baza de date.")

@router.delete("/api/weblinks/{link_id}")
def delete_weblink(link_id: int, db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    link = db.query(models.Weblink).filter(models.Weblink.id == link_id).first()
    if link:
        db.delete(link)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Link-ul nu a fost gasit.")

# ==========================================
# GESTIUNE PARAGRAFE TEXT (MANUALE)
# ==========================================
@router.get("/api/texts")
def get_texts(db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    texts = db.query(models.TextSnippet).all()
    return [{"id": t.id, "content": t.content} for t in texts]

@router.post("/api/texts")
def add_text(req: TextRequest, db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    try:
        new_text = models.TextSnippet(content=req.content)
        db.add(new_text)
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Eroare la salvarea textului.")

@router.put("/api/texts/{text_id}")
def update_text(text_id: int, req: TextRequest, db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    snippet = db.query(models.TextSnippet).filter(models.TextSnippet.id == text_id).first()
    if snippet:
        snippet.content = req.content
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Textul nu a fost gasit.")

@router.delete("/api/texts/{text_id}")
def delete_text(text_id: int, db: Session = Depends(get_db), admin: str = Depends(get_current_admin)):
    snippet = db.query(models.TextSnippet).filter(models.TextSnippet.id == text_id).first()
    if snippet:
        db.delete(snippet)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Textul nu a fost gasit.")

# ==========================================
# GESTIUNE DOCUMENTE PDF
# ==========================================
@router.get("/api/documents")
def get_documents(admin: str = Depends(get_current_admin)):
    if not os.path.exists("date"):
        return []
    files = [f for f in os.listdir("date") if f.lower().endswith(".pdf")]
    return [{"filename": f} for f in files]

@router.post("/api/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), admin: str = Depends(get_current_admin)):
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

@router.delete("/api/documents/{filename}")
def delete_document(filename: str, admin: str = Depends(get_current_admin)):
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

# ==========================================
# RE-INDEXARE AI
# ==========================================
@router.post("/api/reindex")
def reindex_ai(admin: str = Depends(get_current_admin)):
    try:
        reindex_ai_knowledge()
        return {"status": "Re-indexare completata cu succes! AI-ul are acum cunostintele actualizate."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))