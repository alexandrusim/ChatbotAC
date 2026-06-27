import os
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

emb = HuggingFaceEmbeddings(model_name="paraphrase-multilingual-MiniLM-L12-v2")
vs = Chroma(persist_directory="./chroma_db", embedding_function=emb,
            client_settings=Settings(anonymized_telemetry=False, is_persistent=True))

print("Total chunks in store:", vs._collection.count())

q = "locuri mediu rural admitere"
for k in (6, 12):
    print(f"\n===== top {k} =====")
    docs = vs.similarity_search(q, k=k)
    for i, d in enumerate(docs):
        hit = "mediu rural" in d.page_content.lower()
        print(f"[{i}] mediu_rural={hit}  source={d.metadata.get('source')}")