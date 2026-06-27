import os
import asyncio
import pandas as pd
from dotenv import load_dotenv
from chromadb.config import Settings

from langchain_community.document_loaders import PyPDFDirectoryLoader, WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings as LCHuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI 
from langchain_groq import ChatGroq                          

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.embeddings import HuggingFaceEmbeddings as RagasHuggingFaceEmbeddings
from ragas.metrics.collections import Faithfulness, AnswerRelevancy


async def main_evaluation():
    load_dotenv()

    os.environ["USER_AGENT"] = "TUIASI-Chatbot/1.0"

    print(">> [1/4] Incarcare modele si configurare mediu de test hibrid...")
    lc_embeddings = LCHuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")

    db_test_path = "./chroma_db_test"

    if not os.path.exists(db_test_path):
        print(f"   -> Folderul '{db_test_path}' nu exista. Il cream acum din PDF-uri si Site-uri...")

        all_documents = []

        # 1. Incarcare PDF-uri
        if os.path.exists("date"):
            print("      [Sursa] Incarcare documente din folderul 'date'...")
            pdf_loader = PyPDFDirectoryLoader("date")
            pdf_docs = pdf_loader.load()
            all_documents.extend(pdf_docs)
        else:
            print("      [Info] Folderul 'date' nu exista, sarim peste PDF-uri.")

        # 2. Incarcare Site-uri Web
        test_urls = [
            "https://ac.tuiasi.ro/admitere/licenta/",
        ]

        if test_urls:
            print(f"      [Sursa] Scraping text de pe {len(test_urls)} link-uri web...")
            try:
                web_loader = WebBaseLoader(web_paths=test_urls)
                web_docs = web_loader.load()
                all_documents.extend(web_docs)
            except Exception as e:
                print(f"      [Eroare Scraping]: Nu s-au putut descarca site-urile: {e}")

        if not all_documents:
            raise ValueError("Eroare critica: Nu am gasit nici PDF-uri si nu am putut descarca niciun site web!")

        # 3. Impartire text si salvare in baza de date comuna
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(all_documents)

        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=lc_embeddings,
            persist_directory=db_test_path,
            # is_persistent=True => datele se scriu GARANTAT pe disc (altfel raman doar in RAM)
            client_settings=Settings(anonymized_telemetry=False, is_persistent=True)
        )
        print(f"   -> Baza de date hibrida a fost creata cu succes ({len(splits)} chunks)!")
    else:
        print(f"   -> Incarcam baza de date hibrida existenta din '{db_test_path}'...")
        vectorstore = Chroma(
            persist_directory=db_test_path,
            embedding_function=lc_embeddings,
            client_settings=Settings(anonymized_telemetry=False, is_persistent=True)
        )

    retriever = vectorstore.as_retriever(search_kwargs={"k": 6})

    # =====================================================================
    # GENERATOR: model fix (Gemini 3.1 Flash Lite) - cel mai mare RPD din Gemini.
    # Evaluam fidelitatea unui generator controlat, NU a selectiei roulette.
    # =====================================================================
    llm_generator = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite",
        temperature=0.3,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )

    # =====================================================================
    # ARBITRU (JUDGE): model puternic, alt furnizor (Llama 3.3 70B via Groq).
    # Mai fiabil decat 8B la descompunerea in claims + evita self-preference bias.
    # =====================================================================
    openai_client = AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.getenv("GROQ_API_KEY")
    )
    ragas_judge_llm = llm_factory(model="llama-3.3-70b-versatile", client=openai_client)
    ragas_embeddings = RagasHuggingFaceEmbeddings(model="paraphrase-multilingual-MiniLM-L12-v2")

    faithfulness_metric = Faithfulness(llm=ragas_judge_llm)
    answer_relevancy_metric = AnswerRelevancy(llm=ragas_judge_llm, embeddings=ragas_embeddings)

    # =====================================================================
    # PROMPT IDENTIC CU CEL DIN PRODUCTIE (rag_engine.py).
    # Astfel evaluam exact comportamentul aplicatiei, nu un pipeline simplificat.
    # =====================================================================
    system_prompt = (
        "Esti un asistent util, prietenos si concis pentru admiterea la facultate (TUIASI). "
        "Ai voie sa raspunzi STRICT si DOAR pe baza contextului furnizat mai jos. NU folosi cunostintele tale anterioare.\n\n"
        "REGULI IMPORTANTE DE COMPORTAMENT:\n"
        "1. Fii foarte SCURT si LA OBIECT. Foloseste liste cu liniuta (bullet points).\n"
        "2. PRIORITIZEAZA candidatii standard (cetateni romani, absolventi de liceu in Romania).\n"
        "3. Cand esti intrebat de 'acte' sau 'dosar', enumera doar documentele de baza.\n"
        "4. REGULA ANTI-HALUCINATIE: Daca informatia solicitata nu se regaseste clar in contextul de mai jos, NU INCERCA sa ghicesti si NU inventa formule/date. Trebuie sa raspunzi EXACT si DOAR cu textul urmator: 'Nu am gasit aceasta informatie in documentele oficiale actuale. Pentru intrebari specifice, te rugam sa ne contactezi la adresa de email: admitere.ac@groups.tuiasi.ro'. Nu adauga nicio alta propozitie.\n"
        "5. IMPORTANT: Daca gasesti formulele matematice in context, scrie-le in format text simplu (ex: Rezultat = 0.5 * A + 0.5 * B). NU folosi formatare LaTeX si NU pune semnele $.\n"
        "6. Nu confunda acronimele: 'MA' inseamna Media de Admitere, iar 'NTG' inseamna Nota la Testul Grila. Sunt concepte complet diferite.\n"
        "7. REGULA DE SECURITATE (GDPR): NU include si NU repeta in raspunsul tau date personale sensibile oferite de utilizator.\n\n"
        "Context extras din documente:\n{context}"
    )

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
    ])

    # =====================================================================
    # ATENTIE: alege intrebari care SUNT acoperite de documentele tale.
    # Daca o intrebare nu e acoperita, prompt-ul declanseaza refuzul (regula 4),
    # iar Faithfulness poate iesi NaN si AnswerRelevancy aproape 0 (comportament
    # corect, dar iti scade media nejustificat). Verifica acoperirea acestor 8!
    # =====================================================================
    test_questions = [
        "Care este formula pentru media de admitere?",
        "Ce documente trebuie sa contina dosarul de concurs?",
        "Care sunt criteriile de departajare intre candidati?",
        "Ce trebuie sa fac daca nu primesc emailul de confirmare?",
        "Ce facilitati au candidatii olimpici la admitere?",
        "Care sunt taxele de scolarizare si modalitatile de plata?",          # verifica acoperirea
        "Exista locuri speciale pentru candidatii din mediul rural?",          # verifica acoperirea
        "Ce se intampla daca nu confirm locul in termenul stabilit?",          # verifica acoperirea
    ]

    results_list = []

    print("\n>> [2/4] Generare raspunsuri RAG si evaluare imediata...")
    for i, q in enumerate(test_questions):
        docs = retriever.invoke(q)
        context_texts = [doc.page_content for doc in docs]
        context_str = "\n---\n".join(context_texts)

        chain = prompt_template | llm_generator
        answer_msg = chain.invoke({"context": context_str, "input": q})
        generated_answer = answer_msg.content

        print(f"\n   [RAG] Intrebare procesata ({i+1}/{len(test_questions)}): '{q}'")
        print(f"   [Raspuns generat]: {generated_answer[:200]}...")
        print(f"   [Arbitru] Se calculeaza scorurile de halucinatie (judge: Llama 3.3 70B)...")

        try:
            f_res = await faithfulness_metric.ascore(
                user_input=q, response=generated_answer, retrieved_contexts=context_texts
            )
            f_score = f_res.value
        except Exception as e:
            print(f"      [Eroare Faithfulness]: {e}")
            f_score = None

        try:
            ar_res = await answer_relevancy_metric.ascore(
                user_input=q, response=generated_answer
            )
            ar_score = ar_res.value
        except Exception as e:
            print(f"      [Eroare AnswerRelevancy]: {e}")
            ar_score = None

        results_list.append({
            "question": q,
            "answer": generated_answer,
            "contexts": str(context_texts),
            "faithfulness": f_score,
            "answer_relevancy": ar_score
        })

        # Pauza obligatorie: Llama 3.3 70B free tier = 12K TPM, iar Faithfulness
        # consuma mult (2 apeluri + 6 chunks de context). Fara pauza => HTTP 429.
        if i < len(test_questions) - 1:
            print("   [PAUZA ANTI-RATE-LIMIT] Asteptam 65 de secunde...")
            await asyncio.sleep(65)

    print("\n>> [3/4] Salvare raport in 'raport_ragas_halucinatii.csv'...")
    df = pd.DataFrame(results_list)
    df.to_csv("raport_ragas_halucinatii.csv", index=False)

    print("\n================ REZULTATE FINALE EVALUARE ================")
    print(df[["question", "faithfulness", "answer_relevancy"]])

    # Medii (ignora NaN/None, ex. raspunsuri de tip refuz)
    mean_faith = df["faithfulness"].dropna().mean()
    mean_ar = df["answer_relevancy"].dropna().mean()
    print(f"\n>> Faithfulness mediu: {mean_faith:.3f}")
    print(f">> Answer Relevancy mediu: {mean_ar:.3f}")
    print("\n>> [4/4] GATA! Evaluarea s-a terminat cu succes.")


if __name__ == "__main__":
    asyncio.run(main_evaluation())