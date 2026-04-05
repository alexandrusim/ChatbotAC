import os
import random
from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFDirectoryLoader, WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings 
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from database import SessionLocal
from models import Weblink, Conversation

# Load environment variables
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = None

def calculate_model_fitness():
    db = SessionLocal()
    scores = {}
    
    try:
        # Fetch all rated conversations handled by AI
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
            
        # Calculate the average (fitness score)
        for model in sums:
            scores[model] = sums[model] / votes[model]
            
        return scores
    finally:
        db.close()

def get_roulette_wheel_llm():
    """ Official Roulette Wheel Selection implementation """
    
    # 1. Define the "Population" (Available models)
    population = {}
    
    if GOOGLE_API_KEY:
        population["Gemini 2.5 Flash"] = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)
        population["Gemini 3.0 Flash(preview)"] = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0.3)
        population["Gemini 3.1 Flash Lite(preview)"] = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite-preview", temperature=0.3)
    
    if GROQ_API_KEY:
        population["Llama 3.3 (70B)"] = ChatGroq(model_name="llama-3.3-70b-versatile", temperature=0.3)
        population["Llama 3.1 (8B)"] = ChatGroq(model_name="llama-3.1-8b-instant", temperature=0.3)

    if not population:
        raise ValueError("ERROR: No valid API key found in .env!")

    # 2. Get current fitness scores from the database
    current_fitness = calculate_model_fitness()
    
    model_names = list(population.keys())
    roulette_weights = []
    
    # 3. Assign Roulette Weights
    for name in model_names:
        # If a model has no rating yet, give it a baseline fitness of 3.0 out of 5.0
        score = current_fitness.get(name, 3.0)
        roulette_weights.append(score)

    # 4. Spin the wheel!
    winning_model = random.choices(model_names, weights=roulette_weights, k=1)[0]
    
    print(f">> Current roulette scores: {dict(zip(model_names, roulette_weights))}")
    print(f">> The wheel stopped on: {winning_model}")
    
    return winning_model, population[winning_model]

def create_new_vectorstore():
    print(">> Starting information collection (PDF + Web)...")
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
        print(f">> Warning: Web scraping error: {e}")

    all_docs = docs_pdf + docs_web
    
    if not all_docs:
        all_docs = [Document(page_content="Baza de date AI momentan goala.", metadata={"source": "sistem"})]

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(all_docs)

    print(f">> Building AI memory in RAM ({len(splits)} chunks)...")
    return Chroma.from_documents(documents=splits, embedding=embeddings)

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def reindex_ai_knowledge():
    global vectorstore
    print(">> Start Re-indexing in RAM...")
    vectorstore = create_new_vectorstore()
    print(">> Re-indexing finished successfully!")

def get_ai_response(user_message: str):
    global vectorstore
    if vectorstore is None:
        vectorstore = create_new_vectorstore()

    winning_model_name, llm = get_roulette_wheel_llm()
    print(f">> Processing question with model: {winning_model_name}")

    retriever = vectorstore.as_retriever(search_kwargs={"k": 7})

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

    # Construim lantul RAG normal
    rag_chain = (
        {"context": retriever | format_docs, "input": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    
   # === SISTEMUL DE FALLBACK SILENTIOS ===
    try:
        answer = rag_chain.invoke(user_message)
        return answer, winning_model_name
        
    except Exception as e:
        print(f"\n>> [!] EROARE LA MODELUL {winning_model_name}: {e}")
        
        # Fallback Incrucisat (Cross-Provider)
        # Daca a picat Groq (Llama), cerem ajutorul lui Google
        if "Llama" in winning_model_name:
            print(">> [!] INITIEZ FALLBACK SILENTIOS catre Gemini 2.5 Flash...\n")
            fallback_name = "Gemini 2.5 Flash [FALLBACK]"
            fallback_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)
            
        # Daca a picat Google (sau oricare altul), cere ajutorul lui Groq
        else:
            print(">> [!] INITIEZ FALLBACK SILENTIOS catre Llama 3.1 (8B)...\n")
            fallback_name = "Llama 3.1 (8B) [FALLBACK]"
            fallback_llm = ChatGroq(model_name="llama-3.1-8b-instant", temperature=0.3)
        
        # Reconstruim rapid lantul strict pentru modelul de rezerva
        fallback_chain = (
            {"context": retriever | format_docs, "input": RunnablePassthrough()}
            | prompt
            | fallback_llm
            | StrOutputParser()
        )
        
        # Generam raspunsul salvator
        answer = fallback_chain.invoke(user_message)
        
        return answer, fallback_name