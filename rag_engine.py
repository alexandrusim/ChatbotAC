import os
import shutil
from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFDirectoryLoader, WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings 
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

from database import SessionLocal
from models import Weblink

# Incarcare configurari
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("EROARE: Nu am gasit GOOGLE_API_KEY in fisierul .env")

CHROMA_PATH = "./chroma_db"
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

def create_new_vectorstore():
    print("Incep colectarea informatiilor (PDF + Web)...")
    if os.path.exists(CHROMA_PATH):
        shutil.rmtree(CHROMA_PATH)

    loader_pdf = PyPDFDirectoryLoader("date")
    docs_pdf = loader_pdf.load()

    docs_web = []
    try:
        db = SessionLocal()
        urls = db.query(Weblink).filter(Weblink.type == 'url').all()
        db_urls = [u.path for u in urls]
        db.close()

        if db_urls:
            loader_web = WebBaseLoader(db_urls)
            docs_web = loader_web.load()
    except Exception as e:
        print(f"Atentie: Eroare web scraping: {e}")

    all_docs = docs_pdf + docs_web
    if not all_docs:
        raise ValueError("Nu am gasit nicio informatie in folderul 'date' sau in link-uri.")

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(all_docs)

    vectorstore = Chroma.from_documents(
        documents=splits, 
        embedding=embeddings, 
        persist_directory=CHROMA_PATH
    )
    return vectorstore

def load_or_create_vectorstore():
    if os.path.exists(CHROMA_PATH) and os.listdir(CHROMA_PATH):
        print("Am gasit o baza de date vectoriala. O incarc...")
        try:
            vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
            if len(vectorstore.get()['ids']) > 0:
                return vectorstore
        except Exception as e:
            print(f"Eroare la incarcare, refac baza de date: {e}")
    return create_new_vectorstore()

# Variabila globala pentru a tine lantul (chain-ul) RAG incarcat in memorie
rag_chain = None

def build_rag_chain():
    global rag_chain
    vectorstore = load_or_create_vectorstore()
    retriever = vectorstore.as_retriever(search_kwargs={"k": 10}) 
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)

    system_prompt = (
        "Esti un asistent util, prietenos si concis pentru admiterea la facultate (TUIASI). "
        "Raspunde la intrebari STRICT pe baza contextului furnizat mai jos.\n\n"
        "REGULI IMPORTANTE DE COMPORTAMENT:\n"
        "1. Fii foarte SCURT si LA OBIECT. Foloseste liste cu liniuta (bullet points).\n"
        "2. PRIORITIZEAZA candidatii standard (cetateni romani, absolventi de liceu in Romania).\n"
        "3. Cand esti intrebat de 'acte' sau 'dosar', enumera doar documentele de baza.\n"
        "4. Raspunde cu incredere! Daca informatia lipseste COMPLET din context, spune: 'Nu am gasit aceasta informatie in documentele oficiale actuale. Pentru intrebari specifice, te rugam sa ne contactezi la adresa de email: admitere.ac@groups.tuiasi.ro'.\n\n"
        "Context extras din documente:\n{context}"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
    ])

    question_answer_chain = create_stuff_documents_chain(llm, prompt)
    rag_chain = create_retrieval_chain(retriever, question_answer_chain)

def get_ai_response(user_message: str):
    global rag_chain
    if not rag_chain:
        build_rag_chain()
    response = rag_chain.invoke({"input": user_message})
    return response["answer"]

def reindex_ai_knowledge():
    create_new_vectorstore()
    build_rag_chain()