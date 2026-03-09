import os
import shutil
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

os.environ["USER_AGENT"] = "TUIASI-Chatbot/1.0"

# Importuri FastAPI
from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse 
from pydantic import BaseModel

# Importuri LangChain
from langchain_community.document_loaders import PyPDFDirectoryLoader, WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings 
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

# --- 1. CONFIGURARE ---
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("EROARE: Nu am gasit GOOGLE_API_KEY in fisierul .env")

CHROMA_PATH = "./chroma_db"


print("Se incarca modelul de embeddings local (HuggingFace)...")
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

def initialize_vectorstore():
    if os.path.exists(CHROMA_PATH) and os.listdir(CHROMA_PATH):
        print("Am gasit o baza de date salvata. O incarc...")
        try:
            vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
            if len(vectorstore.get()['ids']) > 0:
                return vectorstore
        except Exception as e:
            print(f"Eroare la incarcare, refac baza de date vectoriala: {e}")

    print("Incep colectarea informatiilor (PDF + Web)...")
    if os.path.exists(CHROMA_PATH):
        shutil.rmtree(CHROMA_PATH)

    loader_pdf = PyPDFDirectoryLoader("date")
    docs_pdf = loader_pdf.load()

    docs_web = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT path FROM weblinks WHERE type='url'")
        db_urls = [row[0] for row in cursor.fetchall()]
        conn.close()

        if db_urls:
            loader_web = WebBaseLoader(db_urls)
            docs_web = loader_web.load()
    except Exception as e:
        print(f"Atentie: Eroare web scraping: {e}")

    all_docs = docs_pdf + docs_web
    
    if not all_docs:
        raise ValueError("Nu am gasit nicio informatie.")

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(all_docs)

    vectorstore = Chroma.from_documents(
        documents=splits, 
        embedding=embeddings, 
        persist_directory=CHROMA_PATH
    )
    return vectorstore

# --- 2. INITIALIZARE COMPONENTE AI ---
vectorstore = initialize_vectorstore()
retriever = vectorstore.as_retriever(search_kwargs={"k": 10}) 
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)

system_prompt = (
    "Esti un asistent util, prietenos si concis pentru admiterea la facultate (TUIASI). "
    "Raspunde la intrebari STRICT pe baza contextului furnizat mai jos.\n\n"
    "REGULI IMPORTANTE DE COMPORTAMENT:\n"
    "1. Fii foarte SCURT si LA OBIECT. Foloseste liste cu liniuta (bullet points) pentru a fi usor de citit.\n"
    "2. PRIORITIZEAZA candidatii standard (cetateni romani, absolventi de liceu in Romania). NU oferi informatii despre cetateni straini, romani de pretutindeni sau alte cazuri speciale DECAT daca utilizatorul intreaba explicit despre asta.\n"
    "3. Cand esti intrebat de 'acte' sau 'dosar', enumera doar documentele de baza (diploma, certificat de nastere, buletin, adeverinta medicala, chitanta, etc.).\n"
    "4. Raspunde cu incredere! Daca informatia lipseste COMPLET din context, spune EXACT ASA: 'Nu am gasit aceasta informatie in documentele oficiale actuale. Pentru intrebari specifice, te rugam sa ne contactezi la adresa de email: admitere.ac@groups.tuiasi.ro'. INTERZIS sa trimiti utilizatorul sa caute singur pe site-ul web!\n\n"
    "Context extras din documente:\n{context}"
)

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{input}"),
])

question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, question_answer_chain)


# --- 3. BAZA DE DATE (SQLite) ---
DB_NAME = "chatbot_logs.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. ISTORIC CONVERSATII
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user_message TEXT,
            bot_response TEXT,
            source TEXT
        )
    ''')
    
    # 2. RULES (rule-based)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE,
            response TEXT
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM rules")
    if cursor.fetchone()[0] == 0:
        default_rules = [
            ("contact", "Ne poti contacta la numarul de telefon 0232 278 683 sau prin email la secretariat@ac.tuiasi.ro."),
            ("telefon", "Numarul de telefon al secretariatului AC este 0232 278 683."),
            ("adresa", "Facultatea de Automatica si Calculatoare se afla pe Bulevardul Profesor Dimitrie Mangeron 27, Iasi."),
            ("locatie", "Facultatea se afla pe Bd. Dimitrie Mangeron nr. 27, Iasi."),
            ("program", "Programul secretariatului pentru public este de regula de Luni pana Vineri, in intervalul orar 09:00 - 13:00.")
        ]
        cursor.executemany("INSERT INTO rules (keyword, response) VALUES (?, ?)", default_rules)

    # 3. WEBLINKS (RAG)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weblinks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            path TEXT UNIQUE
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM weblinks")
    if cursor.fetchone()[0] == 0:
        default_urls = [
            ("url", "https://ac.tuiasi.ro/admitere/licenta/"),
            ("url", "https://ac.tuiasi.ro/admitere/masterat/"),
            ("url", "https://www.admitere.tuiasi.ro/licenta/index.php"),
            ("url", "https://www.tuiasi.ro/licenta/")
        ]
        cursor.executemany("INSERT INTO weblinks (type, path) VALUES (?, ?)", default_urls)

    conn.commit()
    conn.close()

# Initializare baza de date
init_db()

def log_conversation(user_msg, bot_msg, source):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        timestp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO conversations (timestamp, user_message, bot_response, source) VALUES (?, ?, ?, ?)",
            (timestp, user_msg, bot_msg, source)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Eroare la salvarea in baza de date: {e}")


# --- 4. CONFIGURARE FASTAPI ---
app = FastAPI(title="Admitere Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- 5. ROUTER-UL (Rule-Based Inteligent) ---
def rule_based_router(message: str):
    msg_lower = message.lower().strip()
    
    if len(msg_lower) > 60:
        return None
        
    greetings = ["salut", "buna", "hey", "hello", "seara", "ziua", "dimineata"]
    if any(greet in msg_lower for greet in greetings) and len(msg_lower) < 25:
        return "Salut! Sunt asistentul virtual pentru admiterea la TUIASI. Cu ce te pot ajuta astazi?"
        
    thanks = ["mersi", "ms", "multumesc", "multam"]
    if any(thx in msg_lower for thx in thanks) and len(msg_lower) < 25:
        return "Cu multa placere! Mult succes la admitere! Daca mai ai intrebari, sunt aici."

    # CITIRE REGULI DIN BAZA DE DATE
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT keyword, response FROM rules")
    db_rules = cursor.fetchall()
    conn.close()
    
    for row in db_rules:
        keyword = row[0]
        fixed_answer = row[1]
        if keyword in msg_lower:
            return fixed_answer
            
    return None

class ChatRequest(BaseModel):
    message: str


# --- 6. ENDPOINT-URI ---
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    user_message = request.message
    
    if not user_message.strip():
        raise HTTPException(status_code=400, detail="Mesajul nu poate fi gol.")
    
    # Rule-Based
    rule_response = rule_based_router(user_message)
    if rule_response:
        log_conversation(user_message, rule_response, "rule-based")
        return {"answer": rule_response, "source": "rule-based"}
    
    # AI RAG
    try:
        response = rag_chain.invoke({"input": user_message})
        ai_answer = response["answer"]
        log_conversation(user_message, ai_answer, "ai-rag")
        return {"answer": ai_answer, "source": "ai-rag"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"status": "Sistemul hibrid este online!"}

@app.get("/chat-ui")
def serve_frontend():
    return FileResponse("index.html")

# Endpoint pentru Dashboard (Istoric conversatii)
@app.get("/logs")
def get_logs():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, user_message, bot_response, source FROM conversations ORDER BY id DESC LIMIT 50")
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            "data": row[0],
            "intrebare_utilizator": row[1],
            "raspuns_bot": row[2],
            "sursa": row[3]
        })
    return {"istoric_conversatii": history}

# ENDPOINT-URI PENTRU DASHBOARD (ADMIN) ---

# --- 7. ENDPOINT-URI PENTRU DASHBOARD (ADMIN) ---

class RuleRequest(BaseModel):
    keyword: str
    response: str

class LinkRequest(BaseModel):
    path: str

@app.get("/dashboard")
def serve_dashboard():
    return FileResponse("dashboard.html")

@app.get("/api/rules")
def get_rules():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, keyword, response FROM rules")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "keyword": r[1], "response": r[2]} for r in rows]

@app.post("/api/rules")
def add_rule(rule: RuleRequest):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO rules (keyword, response) VALUES (?, ?)", (rule.keyword.lower(), rule.response))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ENDPOINT NOU PENTRU STERGERE REGULA
@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM rules WHERE id=?", (rule_id,))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/weblinks")
def get_weblinks():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, type, path FROM weblinks")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "type": r[1], "path": r[2]} for r in rows]

@app.post("/api/weblinks")
def add_weblink(link: LinkRequest):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO weblinks (type, path) VALUES ('url', ?)", (link.path,))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ENDPOINT NOU PENTRU STERGERE LINK
@app.delete("/api/weblinks/{link_id}")
def delete_weblink(link_id: int):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM weblinks WHERE id=?", (link_id,))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/reindex")
def reindex_ai():
    global vectorstore, retriever, rag_chain
    try:
        vectorstore = initialize_vectorstore()
        retriever = vectorstore.as_retriever(search_kwargs={"k": 10})
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)
        return {"status": "Re-indexare completata cu succes! AI-ul are acum cunostintele actualizate."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ENDPOINT NOU PENTRU PDF-URI

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
    # Securitate: prevenire stergere fisiere din alte directoare
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nume de fisier invalid.")
    
    file_path = os.path.join("date", filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return {"status": "success"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=404, detail="Fisierul nu a fost gasit.")