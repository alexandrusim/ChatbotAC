# Chatbot Admitere TUIASI

Acesta este un sistem inteligent de asistență virtuală pentru informații despre admiterea la Facultatea de Automatică și Calculatoare (TUIASI) din cadrul Universității Tehnice "Gheorghe Asachi" din Iași.

Sistemul a fost proiectat pe o arhitectură bazată pe containere (Docker) și integrează algoritmi dinamici de rutare a modelelor de limbaj.

## Descriere

Aplicația utilizează un sistem hibrid și adaptiv de răspunsuri:
- **Rule-based**: Pentru întrebări administrative simple, unde răspunsurile sunt predefinite și fixe.
- **AI RAG (Retrieval-Augmented Generation)**: Pentru întrebări complexe bazate pe documentele și regulamentele oficiale. Utilizează LangChain, ChromaDB pentru indexarea vectorială și extragerea contextului.
- **Roulette Wheel Selection (Algoritm Genetic)**: Selecția modelului LLM la fiecare interogare se face dinamic, proporțional cu scorul de "fitness" (media notelor de feedback primite de la utilizatori în timp real).
- **Cross-Provider Silent Fallback**: Un sistem de înaltă disponibilitate (High Availability). Dacă un model (ex: Google Gemini) atinge limitele de acces sau returnează o eroare, cererea este rutată invizibil către un model de rezervă (ex: Groq Llama), garantând funcționarea continuă fără erori în interfață.

## Cerințe Sistem

Sistemul este complet containerizat. Nu este necesară instalarea locală a limbajului Python sau a bazelor de date.
- **Docker Desktop** (sau Docker Engine & Docker Compose)
- Conexiune la internet pentru API-urile LLM și procesul de web-scraping
- Cheie API Google Generative AI (Gemini)
- Cheie API Groq (Llama)

## Instalare

1. Clonează repository-ul proiectului în calculatorul tău.

2. Creează un fișier `.env` în directorul rădăcină al proiectului și adaugă variabilele de mediu:
   ```env
   # API Keys
   GOOGLE_API_KEY=cheia_ta_google_aici
   GROQ_API_KEY=cheia_ta_groq_aici

   # Database Configuration
   DB_USER=root
   DB_PASSWORD=parola_dorita
   DB_DATABASE=chatbot_db
   ```

3. Plasează documentele PDF inițiale (ex: regulamentul de admitere) în folderul `date/` pentru a putea fi indexate la prima pornire.

## Rulare

1. Deschide terminalul în folderul rădăcină al proiectului.

2. Construiește imaginile și pornește containerele în fundal:
   ```bash
   docker compose build --no-cache
   docker compose up -d
   ```

3. Accesarea interfețelor în browser:
   - **Interfața utilizator (Chatbot)**: `http://localhost:8000/chat-ui` 
   - **Panoul de administrare (Dashboard)**: `http://localhost:8000/dashboard`

4. Pentru a opri sistemul:
   ```bash
   docker compose down
   ```

## Funcționalități

- **Dashboard Administrativ**: Interfață web dedicată pentru gestionarea regulilor fixe, vizualizarea istoricului detaliat (inclusiv ce model a generat răspunsul și nota primită) și managementul surselor.
- **Gestiune Surse de Date**: Încărcare de fișiere PDF și adăugare de link-uri URL (pentru web-scraping) direct din interfața de administrare.
- **Bază de date Relațională**: Stocare persistentă în MariaDB/MySQL a conversațiilor, surselor și regulilor.
- **Re-indexare Manuală**: Control precis asupra momentului în care AI-ul recalculează baza de date vectorială în memoria RAM (ChromaDB).

## Note Importante

- La prima rulare a containerelor, baza de date MySQL se va inițializa complet goală (fără istoric sau reguli predefinite).
- Orice modificare a fișierelor PDF din folderul `date/` sau orice modificare a link-urilor URL din Dashboard necesită apăsarea butonului "RE-INDEXEAZA BAZA DE DATE AI" din Dashboard pentru a actualiza cunoștințele asistentului virtual.