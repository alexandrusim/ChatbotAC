import os
import shutil
from fastapi import APIRouter, HTTPException, File, UploadFile, Depends
from fastapi.responses import FileResponse 
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
import models
from rule_based import rule_based_router
from rag_engine import get_ai_response, reindex_ai_knowledge


router = APIRouter()

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
        ai_answer = get_ai_response(user_message)
        log = models.Conversation(user_message=user_message, bot_response=ai_answer, source="ai-rag")
        db.add(log)
        db.commit()
        db.refresh(log) 
        return {"answer": ai_answer, "source": "ai-rag", "conversation_id": log.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ENDPOINT-URI PENTRU DASHBOARD (ADMIN)

@router.get("/dashboard")
def serve_dashboard():
    return FileResponse("frontend/dashboard.html")

@router.get("/logs")
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

@router.get("/api/rules")
def get_rules(db: Session = Depends(get_db)):
    rules = db.query(models.Rule).all()
    return [{"id": r.id, "keyword": r.keyword, "response": r.response} for r in rules]

@router.post("/api/rules")
def add_rule(rule: RuleRequest, db: Session = Depends(get_db)):
    try:
        new_rule = models.Rule(keyword=rule.keyword.lower(), response=rule.response)
        db.add(new_rule)
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Cuvantul cheie exista deja sau eroare de baza de date.")

@router.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(models.Rule).filter(models.Rule.id == rule_id).first()
    if rule:
        db.delete(rule)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Regula nu a fost gasita.")


# SURSE WEB (LINK-URI)

@router.get("/api/weblinks")
def get_weblinks(db: Session = Depends(get_db)):
    links = db.query(models.Weblink).all()
    return [{"id": l.id, "type": l.type, "path": l.path} for l in links]

@router.post("/api/weblinks")
def add_weblink(link: LinkRequest, db: Session = Depends(get_db)):
    try:
        new_link = models.Weblink(path=link.path)
        db.add(new_link)
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Link-ul exista deja sau eroare de baza de date.")

@router.delete("/api/weblinks/{link_id}")
def delete_weblink(link_id: int, db: Session = Depends(get_db)):
    link = db.query(models.Weblink).filter(models.Weblink.id == link_id).first()
    if link:
        db.delete(link)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Link-ul nu a fost gasit.")


# RE-INDEXARE AI

@router.post("/api/reindex")
def reindex_ai():
    try:
        reindex_ai_knowledge()
        return {"status": "Re-indexare completata cu succes! AI-ul are acum cunostintele actualizate."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# GESTIUNE DOCUMENTE PDF

@router.get("/api/documents")
def get_documents():
    if not os.path.exists("date"):
        return []
    files = [f for f in os.listdir("date") if f.lower().endswith(".pdf")]
    return [{"filename": f} for f in files]

@router.post("/api/upload-pdf")
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

@router.delete("/api/documents/{filename}")
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

@router.post("/feedback/{conversation_id}")
def submit_feedback(conversation_id: int, feedback: FeedbackRequest, db: Session = Depends(get_db)):
    conv = db.query(models.Conversation).filter(models.Conversation.id == conversation_id).first()
    
    if not conv:
        raise HTTPException(status_code=404, detail="Conversatia nu a fost gasita.")
        
    conv.rating = feedback.rating
    db.commit()
    
    return {"message": "Feedback salvat cu succes!", "rating": feedback.rating}