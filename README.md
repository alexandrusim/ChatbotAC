# Chatbot Admitere TUIASI

Acesta este un chatbot inteligent pentru informații despre admiterea la Facultatea de Automatică și Calculatoare (TUIASI) de la Universitatea Tehnică "Gheorghe Asachi" din Iași.

## Descriere

Aplicația utilizează un sistem hibrid de răspunsuri:
- **Rule-based**: Pentru întrebări simple și răspunsuri fixe (salutări, contact, etc.)
- **AI RAG (Retrieval-Augmented Generation)**: Pentru întrebări complexe, folosind LangChain, ChromaDB pentru vector store, și Google Gemini pentru generarea răspunsurilor.

Backend-ul este construit cu FastAPI, iar interfața web este simplă și responsive.

## Cerințe Sistem

- Python 3.8+
- Cheie API Google Generative AI (Gemini)

## Instalare

1. Clonează repository-ul sau descarcă fișierele.

2. Instalează dependențele:
   ```
   pip install -r requirements.txt
   ```

3. Creează un fișier `.env` în directorul rădăcină și adaugă cheia API Google:
   ```
   GOOGLE_API_KEY=your_google_api_key_here
   ```

4. Plasează documentele PDF în folderul `date/` pentru a fi încărcate în baza de date vectorială.

## Rulare

1. Activează mediul virtual:
   ```
   source .venv/bin/activate
   ```

2. Rulează serverul:
   ```
   uvicorn main:app --reload
   ```
3. Deschide browser-ul la `http://localhost:8000/chat-ui` pentru interfața web.

API-ul este disponibil la `http://localhost:8000` cu endpoint-ul `/chat` pentru POST requests.

## Structura Proiect

- `main.py`: Codul principal al serverului FastAPI
- `check_models.py`: Script pentru verificarea modelelor disponibile Google Gemini
- `index.html`: Interfața web simplă
- `date/`: Folder pentru documente PDF
- `chroma_db/`: Baza de date vectorială (se generează automat)

## Funcționalități

- Încărcare automată de documente PDF și web
- Împărțire inteligentă a textului
- Embeddings locale cu HuggingFace
- Răspunsuri rapide pentru întrebări comune
- Interfață web ușor de utilizat

## Note

- Asigură-te că ai acces la internet pentru scraping-ul web și API-ul Google.
- Baza de date se reconstruiește dacă folderul `chroma_db` este gol sau corupt.
