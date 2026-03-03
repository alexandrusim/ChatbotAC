import os
import shutil
from dotenv import load_dotenv

# Rezolva avertismentul cu USER_AGENT
os.environ["USER_AGENT"] = "TUIASI-Chatbot/1.0"

# Importuri FastAPI
from fastapi import FastAPI, HTTPException
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

# 1. Configurare
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("EROARE: Nu am gasit GOOGLE_API_KEY in fisierul .env")

CHROMA_PATH = "./chroma_db"
URLS = [
    "https://ac.tuiasi.ro/admitere/licenta/",
    "https://ac.tuiasi.ro/admitere/masterat/", 
    "https://www.admitere.tuiasi.ro/licenta/index.php",
    "https://www.tuiasi.ro/licenta/"
]

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
            print(f"Eroare la incarcare, refac baza de date: {e}")

    print("Incep colectarea informatiilor (PDF + Web)...")
    if os.path.exists(CHROMA_PATH):
        shutil.rmtree(CHROMA_PATH)

    loader_pdf = PyPDFDirectoryLoader("date")
    docs_pdf = loader_pdf.load()

    docs_web = []
    try:
        loader_web = WebBaseLoader(URLS)
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

# --- INITIALIZARE COMPONENTE AI ---
vectorstore = initialize_vectorstore()
# Am crescut numarul de paragrafe extrase la 10 pentru precizie
retriever = vectorstore.as_retriever(search_kwargs={"k": 10}) 
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)

system_prompt = (
    "Esti un asistent util, prietenos si concis pentru admiterea la facultate (TUIASI). "
    "Raspunde la intrebari STRICT pe baza contextului furnizat mai jos.\n\n"
    "REGULI IMPORTANTE DE COMPORTAMENT:\n"
    "1. Fii foarte SCURT si LA OBIECT. Foloseste liste cu liniuta (bullet points) pentru a fi usor de citit.\n"
    "2. PRIORITIZEAZA candidatii standard (cetateni romani, absolventi de liceu in Romania). NU oferi informatii despre cetateni straini, romani de pretutindeni sau alte cazuri speciale DECAT daca utilizatorul intreaba explicit despre asta.\n"
    "3. Cand esti intrebat de 'acte' sau 'dosar', enumera doar documentele de baza (diploma, certificat de nastere, buletin, adeverinta medicala, chitanta, etc.).\n"
    "4. Raspunde cu incredere! Daca informatia lipseste COMPLET din context, spune DOAR: 'Nu am gasit aceasta informatie in documentele oficiale actuale.' INTERZIS sa trimiti utilizatorul sa consulte site-ul web, pentru ca tu esti aici sa faci asta in locul lui!\n\n"
    "Context extras din documente:\n{context}"
)

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{input}"),
])

question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, question_answer_chain)

# --- CONFIGURARE FASTAPI ---
app = FastAPI(title="Admitere Chatbot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTER-UL (Rule-Based Inteligent & Raspunsuri Fixe) ---
def rule_based_router(message: str):
    msg_lower = message.lower().strip()
    
    # 1. Daca mesajul e foarte lung, clar e o intrebare complexa -> Trimite la AI
    if len(msg_lower) > 60:
        return None
        
    # 2. Gestionarea Saluturilor
    greetings = ["salut", "buna", "hey", "hello", "seara", "ziua", "dimineata"]
    if any(greet in msg_lower for greet in greetings) and len(msg_lower) < 25:
        return "Salut! Sunt asistentul virtual pentru admiterea la TUIASI. Cu ce te pot ajuta astazi?"
        
    # 3. Gestionarea Multumirilor
    thanks = ["mersi", "ms", "multumesc", "multam"]
    if any(thx in msg_lower for thx in thanks) and len(msg_lower) < 25:
        return "Cu multa placere! Mult succes la admitere! Daca mai ai intrebari, sunt aici."

    # 4. Sistem de Cautare Exacta pentru Raspunsuri Fixe
    # Aici definim cuvintele cheie si raspunsurile predefinite
    fixed_responses = {
        "contact": "Ne poti contacta la numarul de telefon 0232 278 683 sau prin email la secretariat@ac.tuiasi.ro.",
        "telefon": "Numarul de telefon al secretariatului AC este 0232 278 683.",
        "adresa": "Facultatea de Automatica si Calculatoare se afla pe Bulevardul Profesor Dimitrie Mangeron 27, Iasi.",
        "locatie": "Facultatea se afla pe Bd. Dimitrie Mangeron nr. 27, Iasi.",
        "program": "Programul secretariatului pentru public este de regula de Luni pana Vineri, in intervalul orar 09:00 - 13:00."
    }
    
    # Verificam daca vreun cuvant cheie se afla in mesaj
    for keyword, fixed_answer in fixed_responses.items():
        # Cautam cuvantul exact ca de sine statator (sa nu fie parte din alt cuvant)
        # ex: "contact" sa fie gasit in "care este adresa de contact?"
        if keyword in msg_lower:
            return fixed_answer
            
    # Daca nu se potriveste nicio regula fixa, returnam None (Mecanismul de Fallback catre AI)
    return None

class ChatRequest(BaseModel):
    message: str

# --- ENDPOINT-URI ---
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    user_message = request.message
    
    if not user_message.strip():
        raise HTTPException(status_code=400, detail="Mesajul nu poate fi gol.")
    
    # 1. Rule-Based
    rule_response = rule_based_router(user_message)
    if rule_response:
        return {"answer": rule_response, "source": "rule-based"}
    
    # 2. AI RAG
    try:
        response = rag_chain.invoke({"input": user_message})
        return {"answer": response["answer"], "source": "ai-rag"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"status": "Sistemul hibrid este online!"}

# --- ENDPOINT PENTRU INTERFATA WEB ---
@app.get("/chat-ui")
def serve_frontend():
    return FileResponse("index.html")