import os
from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFDirectoryLoader, WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings 
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document

# Am importat componentele de baza LCEL pentru a construi lantul manual
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from database import SessionLocal
from models import Weblink

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

rag_chain = None
vectorstore = None

def create_new_vectorstore():
    print(">> Incep colectarea informatiilor (PDF + Web)...")
    
    if not os.path.exists("date"):
        os.makedirs("date")

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
        print(f">> Atentie: Eroare web scraping: {e}")

    all_docs = docs_pdf + docs_web
    
    if not all_docs:
        all_docs = [Document(page_content="Baza de date AI momentan goala.", metadata={"source": "sistem"})]

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(all_docs)

    print(f">> Construiesc memoria AI in RAM ({len(splits)} fragmente)...")
    vs = Chroma.from_documents(documents=splits, embedding=embeddings)
    return vs

# Functie utilitara care transforma lista de documente intr-un singur string
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def build_rag_chain(vs_nou=None):
    global rag_chain, vectorstore
    
    if vs_nou is not None:
        vectorstore = vs_nou
    elif vectorstore is None:
        vectorstore = create_new_vectorstore()

    print(">> Initializez LLM si Retriever...")
    retriever = vectorstore.as_retriever(search_kwargs={"k": 10}) 
    
    # Am revenit oficial la versiunea ta castigatoare!
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

    print(">> Construiesc QA Chain manual (LCEL)...")
    
    # Asamblarea clara, fara functii "black-box" care sa dea crash aiurea
    rag_chain = (
        {"context": retriever | format_docs, "input": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    
    print(">> Lantul AI a fost construit cu succes!")

def get_ai_response(user_message: str):
    global rag_chain
    if not rag_chain:
        build_rag_chain()
    
    # Noul nostru lant inteligent returneaza raspunsul ca string direct
    answer = rag_chain.invoke(user_message)
    return answer

def reindex_ai_knowledge():
    print(">> Start Re-indexare in RAM...")
    nou_vectorstore = create_new_vectorstore()
    build_rag_chain(vs_nou=nou_vectorstore)
    print(">> Re-indexare finalizata complet si in siguranta!")