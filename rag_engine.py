import os
import random
import spacy
import chromadb
import threading 
from chromadb.config import Settings
from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFDirectoryLoader, WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings 
from langchain_chroma import Chroma 
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from database import SessionLocal
from models import Weblink, Conversation, TextSnippet

# Load environment variables
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "langchain"



_embeddings_model = None
vectorstore = None
_nlp_spacy = None
_chroma_client = None  # Clientul persistent unic
_rag_lock = threading.Lock() # Lacatul pentru Thread-Safety

def get_embeddings():
    global _embeddings_model
    if _embeddings_model is None:
        print(">> [RAG] Se incarca modelul de Embeddings...")
        _embeddings_model = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")
    return _embeddings_model

def get_spacy():
    global _nlp_spacy
    if _nlp_spacy is None:
        print(">> [RAG] Se incarca modelul NLP spaCy...")
        _nlp_spacy = spacy.load("ro_core_news_sm")
    return _nlp_spacy

def get_chroma_client():
    """Returneaza un singur client ChromaDB persistent (scrie GARANTAT pe disc)."""
    global _chroma_client
    if _chroma_client is None:
        print(">> [RAG] Se initializeaza clientul ChromaDB persistent...")
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False)
        )
    return _chroma_client


def corecteaza_vocabular_student(mesaj: str) -> str:
    """Intercepteaza si inlocuieste sintagmele studentilor cu termeni academici oficiali."""
    nlp = get_spacy()
    
    mesaj_lower = mesaj.lower()
    
    fraze_sinonime = {
        "nota la admitere": "media de admitere",
        "nota de admitere": "media de admitere",
        "nota finala": "media de admitere",
        "actele necesare": "dosarul de inscriere",
        "hartiile pentru": "actele pentru",
        "sa intru la": "sa fiu admis la"
    }
    
    mesaj_corectat = mesaj_lower
    for gresit, corect in fraze_sinonime.items():
        mesaj_corectat = mesaj_corectat.replace(gresit, corect)
            
    return mesaj_corectat

def calculate_model_fitness():
    db = SessionLocal()
    scores = {}
    
    try:
        history = db.query(Conversation.source, Conversation.rating).filter(
            Conversation.source.like('ai-rag%'),
            Conversation.rating != None
        ).all()
        
        sums = {}
        votes = {}
        
        for source, rating in history:
            if source.startswith("ai-rag (") and source.endswith(")"):
                model_name = source[8:-1]
            else:
                model_name = source
            
            sums[model_name] = sums.get(model_name, 0) + rating
            votes[model_name] = votes.get(model_name, 0) + 1
            
        for model in sums:
            scores[model] = sums[model] / votes[model]
            
        return scores
    finally:
        db.close()

def get_roulette_wheel_llm():
    """ Official Roulette Wheel Selection implementation """
    population = {}
    
    if GOOGLE_API_KEY:
        population["Gemini 3.5 Flash"] = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0.3)
        population["Gemini 3.0 Flash (preview)"] = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.3)
        population["Gemini 3.1 Flash Lite"] = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", temperature=0.3)
    
    if GROQ_API_KEY:
        population["Llama 3.3 (70B)"] = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.3)
        population["Llama 3.1 (8B)"] = ChatGroq(model_name="llama-3.1-8b-instant", temperature=0.3)

    if not population:
        raise ValueError("ERROR: No valid API key found in .env!")

    current_fitness = calculate_model_fitness()
    
    model_names = list(population.keys())
    roulette_weights = []
    
    SHARPNESS = 2  

    for name in model_names:
        # Scor neutru 3.0 pentru modelele inca neevaluate
        score = current_fitness.get(name, 3.0)
        roulette_weights.append(score ** SHARPNESS)

    winning_model = random.choices(model_names, weights=roulette_weights, k=1)[0]
    
    print(f">> Current roulette scores: {dict(zip(model_names, roulette_weights))}")
    print(f">> The wheel stopped on: {winning_model}")
    
    return winning_model, population[winning_model]

def create_new_vectorstore():
    print(">> Starting information collection (PDF + Web + Text)...")
    if not os.path.exists("date"): 
        os.makedirs("date")
    
    loader_pdf = PyPDFDirectoryLoader("date")
    docs_pdf = loader_pdf.load()
    
    docs_web = []
    docs_text = [] 
    
    try:
        db = SessionLocal()
        
        urls = db.query(Weblink).filter(Weblink.type == 'url').all()
        db_urls = [u.path for u in urls]
        if db_urls:
            loader_web = WebBaseLoader(db_urls)
            docs_web = loader_web.load()
            
        snippets = db.query(TextSnippet).all()
        for snippet in snippets:
            doc = Document(
                page_content=snippet.content, 
                metadata={"source": "text_manual", "id": snippet.id}
            )
            docs_text.append(doc)
            
        db.close()
    except Exception as e:
        print(f">> Warning: Data collection error (Web/Text): {e}")

    all_docs = docs_pdf + docs_web + docs_text
    
    if not all_docs:
        all_docs = [Document(page_content="Baza de date AI momentan goala.", metadata={"source": "sistem"})]

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(all_docs)

    print(f">> Building AI memory on DISK ({len(splits)} chunks)...")
    
    client = get_chroma_client()
    try:
        client.delete_collection(COLLECTION_NAME)
        print(">> [RAG] Memoria veche a fost golita curat din baza de date.")
    except Exception:
        # Prima rulare sau colectie inexistenta
        pass
        
    return Chroma.from_documents(
        documents=splits, 
        embedding=get_embeddings(),
        client=client,
        collection_name=COLLECTION_NAME,
    )

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def reindex_ai_knowledge():
    global vectorstore
    print(">> Start Re-indexing...")
    
    with _rag_lock: 
        # Eliberare lock-ul din RAM inainte de a sterge datele
        if vectorstore is not None:
            vectorstore = None
            
        vectorstore = create_new_vectorstore()
        
    print(">> Re-indexing finished successfully!")

def get_ai_response(user_message: str):
    global vectorstore
    
    # Pattern Double-Checked Locking pentru stabilitate sub stress 
    if vectorstore is None:
        with _rag_lock: # Blocare celelalte thread-uri pana cand se termina incarcarea
            if vectorstore is None: 
                client = get_chroma_client()
                # Verificare daca exista deja o colectie cu date pe disc
                existing_collections = [c.name for c in client.list_collections()]
                if COLLECTION_NAME in existing_collections:
                    print(">> [RAG] Incarcam memoria AI direct de pe disc (foarte rapid)...")
                    vectorstore = Chroma(
                        client=client,
                        embedding_function=get_embeddings(),
                        collection_name=COLLECTION_NAME,
                    )
                else:
                    print(">> [RAG] Memoria lipseste. Se porneste re-indexarea automata...")
                    vectorstore = create_new_vectorstore()

    mesaj_procesat = corecteaza_vocabular_student(user_message)
    if mesaj_procesat != user_message.lower():
        print(f"\n>> [!] Input original: {user_message}")
        print(f">> [!] Input tradus semantic: {mesaj_procesat}")

    winning_model_name, llm = get_roulette_wheel_llm()
    print(f">> Processing question with model: {winning_model_name}")

    retriever = vectorstore.as_retriever(search_kwargs={"k": 12})



    system_prompt = (
        "Esti un asistent util, prietenos si concis pentru admiterea la facultate (TUIASI). "
        "Ai voie sa raspunzi STRICT si DOAR pe baza contextului furnizat mai jos. NU folosi cunostintele tale anterioare.\n\n"
        "REGULI IMPORTANTE DE COMPORTAMENT:\n"
        "1. Fii foarte SCURT si LA OBIECT. Foloseste liste cu liniuta (bullet points).\n"
        "2. PRIORITIZEAZA candidatii standard (cetateni romani, absolventi de liceu in Romania).\n"
        "3. Cand esti intrebat de 'acte' sau 'dosar', enumera doar documentele de baza.\n"
        "4. REGULA ANTI-HALUCINATIE: Daca informatia solicitata nu se regaseste clar in contextul de mai jos, NU INCERCA sa ghicesti si NU inventa formule/date. Trebuie sa raspunzi EXACT si DOAR cu textul urmator: 'Nu am gasit aceasta informatie in documentele oficiale actuale. Pentru intrebari specifice, te rugam sa ne contactezi la adresa de email: admitere.ac@groups.tuiasi.ro'. Nu adauga nicio alta propozitie.\n"
        "5. IMPORTANT: Daca gasesti formulele matematice in context, scrie-le in format text simplu (ex: Rezultat = 0.5 * A + 0.5 * B). NU folosi formatare LaTeX si NU pune semnele $.\n"
        "6. Nu confunda acronimele: 'MA' înseamnă Media de Admitere, iar 'NTG' înseamnă Nota la Testul Grilă. Sunt concepte complet diferite.\n"
        "7. REGULA DE SECURITATE (GDPR): NU include si NU repeta in raspunsul tau date personale sensibile oferite de utilizator.\n\n"
        "Context extras din documente:\n{context}"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
    ])

    rag_chain = (
        {"context": retriever | format_docs, "input": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    
    try:
        answer = rag_chain.invoke(mesaj_procesat)
        return answer, winning_model_name
        
    except Exception as e:
        print(f"\n>> [!] EROARE LA MODELUL {winning_model_name}: {e}")
        
        if "Llama" in winning_model_name:
            print(">> [!] INITIEZ FALLBACK SILENTIOS catre Gemini 3.5 Flash...\n")
            fallback_name = "Gemini 3.5 Flash [FALLBACK]"
            fallback_llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0.3)
            
        else:
            print(">> [!] INITIEZ FALLBACK SILENTIOS catre Llama 3.1 (8B)...\n")
            fallback_name = "Llama 3.1 (8B) [FALLBACK]"
            fallback_llm = ChatGroq(model_name="llama-3.1-8b-instant", temperature=0.3)
        
        fallback_chain = (
            {"context": retriever | format_docs, "input": RunnablePassthrough()}
            | prompt
            | fallback_llm
            | StrOutputParser()
        )
        
        answer = fallback_chain.invoke(mesaj_procesat)
        return answer, fallback_name