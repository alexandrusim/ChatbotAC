# Chatbot Admitere TUIASI - Sistem Inteligent RAG

Acesta este un sistem inteligent de asistență virtuală pentru informații despre admiterea la Facultatea de Automatică și Calculatoare (TUIASI) din cadrul Universității Tehnice "Gheorghe Asachi" din Iași.

Sistemul a fost proiectat pe o arhitectură bazată pe containere (Docker) și integrează algoritmi dinamici de rutare a modelelor de limbaj, procesare de limbaj natural (NLP) și generare augmentată prin recuperare (RAG).

##  Arhitectură și Funcționalități Cheie

Aplicația utilizează un sistem hibrid, securizat și adaptiv de răspunsuri:

- **Sistem RAG (Retrieval-Augmented Generation) Optimizat**: Utilizează LangChain și ChromaDB (cu persistență pe disc, prin `PersistentClient`) pentru indexarea vectorială a contextului (k=12). Embeddings-urile sunt generate local cu modelul `paraphrase-multilingual-MiniLM-L12-v2` (HuggingFace). Suportă citirea din PDF-uri, Web Scraping (URL-uri) și texte introduse manual.
- **Lazy Loading & Persistență**: Baza de date vectorială și modelele grele (Embeddings, NLP) nu se încarcă la pornirea serverului pentru a economisi resurse, ci sunt stocate local (`./chroma_db`) și încărcate la cerere (cold start), protejate de un mecanism Double-Checked Locking pentru siguranța firelor de execuție.
- **Interceptor Semantic (spaCy)**: Traduce automat „limbajul studențesc” în termeni academici oficiali (ex: transformă *"nota de admitere"* în *"media de admitere"*) înainte de a interoga AI-ul, crescând precizia răspunsurilor.
- **Roulette Wheel Selection**: Selecția modelului LLM la fiecare interogare se face dinamic, proporțional cu scorul de "fitness" (media notelor de feedback primite de la utilizatori, pe o scară de 1-5 stele), ascuțit printr-un factor de putere (`SHARPNESS`) pentru a favoriza modelele cu performanță mai bună, păstrând totuși explorarea.
- **Cross-Provider Silent Fallback (High Availability)**: Dacă un model (ex: Google Gemini) atinge limitele de acces sau returnează o eroare, cererea este rutată invizibil către un model de rezervă (ex: Groq Llama), garantând funcționarea continuă fără erori în interfață.
- **Modul Secretariat (Generare E-mailuri)**: Un instrument intern pentru personalul administrativ ce generează automat răspunsuri oficiale la e-mailurile studenților, incluzând protecție GDPR la nivel de prompt pentru filtrarea datelor cu caracter personal (CNP, Nume, Telefon etc.).
- **Securitate JWT**: Panoul de administrare este complet protejat prin autentificare cu token-uri JSON Web Tokens.

---

##  Cerințe Sistem

Sistemul backend este complet containerizat. Nu este necesară instalarea locală a limbajului Python sau a bazelor de date.
- **Docker Desktop** (sau Docker Engine & Docker Compose)
- Conexiune la internet pentru API-urile LLM și procesul de web-scraping
- Chei API valide: Google Generative AI (Gemini), Groq (Llama) și HuggingFace (pentru Embeddings)

---

##  Instalare și Configurare

1. Clonează / dezarhivează proiectul pe calculatorul tău.
2. Creează un fișier `.env` în directorul rădăcină al proiectului (lângă `docker-compose.yml`) și adaugă variabilele de mediu obligatorii:

```env
   # API Keys (Inteligenta Artificiala)
   GOOGLE_API_KEY=cheia_ta_google_aici
   GROQ_API_KEY=cheia_ta_groq_aici
   HF_TOKEN=cheia_ta_huggingface_aici

   # Securitate si Autentificare Dashboard
   JWT_SECRET_KEY=un_cod_secret_foarte_lung_si_aleatoriu
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=parola_dorita_pentru_panou

   # Database Configuration (MariaDB)
   DB_ROOT_PASSWORD=parola_root_dorita
   DB_USER=tuiasi_user
   DB_PASSWORD=parola_user_dorita
   DB_DATABASE=chatbot_db
```

3. Plasează documentele PDF oficiale (ex: regulamentul de admitere) în folderul `date/`.

---

##  Rularea Serverului (Docker)

1. Deschide terminalul în folderul rădăcină al proiectului.
2. Construiește imaginile și pornește containerele în fundal:
```bash
   docker compose up --build -d
```
3. Așteaptă 1-2 minute pentru ca MariaDB să se inițializeze și API-ul FastAPI să devină disponibil.
4. **FOARTE IMPORTANT (La prima rulare):**
   - Accesează panoul de administrare la `http://localhost:8000/static/login.html`
   - Loghează-te cu credențialele din fișierul `.env`.
   - Mergi în tab-ul **Surse AI (RAG)** și apasă butonul roșu **RE-INDEXEAZA BAZA DE DATE AI**.
   - Acest pas va citi PDF-urile tale și va construi "memoria" AI-ului local, pe PC-ul tău. Fără acest pas, chat-ul public va spune că nu știe să răspundă.

> **Notă (fus orar):** Containerul `web` este configurat cu `TZ=Europe/Bucharest` (în `docker-compose.yml`), iar imaginea instalează `tzdata` (în `Dockerfile`), astfel încât timestamp-urile conversațiilor din dashboard să reflecte ora locală a României.

---

##  Integrarea în WordPress (Frontend)

Sistemul oferă un widget plutitor asincron, perfect integrabil în orice site WordPress, fără a îngreuna încărcarea paginilor.

**Pași de integrare:**
1. Accesează panoul de control WordPress (`/wp-admin`).
2. Există două variante pentru a adăuga codul:
   - Fie folosești un plugin precum **Insert Headers and Footers** (sau WPCode) și adaugi codul în secțiunea *Footer*.
   - Fie adaugi un bloc de tip **HTML Personalizat (Custom HTML)** în subsolul temei (Footer Widget).
3. Lipește următorul cod complet:

```html
<style>
  #chatbot-container {
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 99999;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
  }
  
  #chatbot-iframe {
    display: none;
    width: 380px;
    height: 550px;
    border: none;
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.2);
    margin-bottom: 15px;
    transition: all 0.3s ease-in-out;
    background-color: white;
  }

  #chatbot-toggle {
    background-color: #0056b3;
    color: white;
    border: none;
    border-radius: 50%;
    width: 65px;
    height: 65px;
    font-size: 28px;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    transition: transform 0.2s;
    display: flex;
    justify-content: center;
    align-items: center;
  }
  
  #chatbot-toggle:hover {
    transform: scale(1.1);
  }

  #chatbot-maximize {
    display: none;
    position: absolute;
    top: 12px;
    right: 20px;
    background: transparent;
    border: none;
    color: white; 
    font-size: 20px;
    cursor: pointer;
    z-index: 100000;
    transition: transform 0.2s;
  }
  
  #chatbot-maximize:hover {
    transform: scale(1.2);
  }

  /* Stari */
  .chatbot-open #chatbot-iframe { display: block; }
  .chatbot-open #chatbot-maximize { display: block; }

  /* Modul Fullscreen */
  .chatbot-fullscreen {
    top: 0 !important;
    left: 0 !important;
    bottom: 0 !important;
    right: 0 !important;
    width: 100% !important;
    height: 100% !important;
    background-color: white;
  }
  
  .chatbot-fullscreen #chatbot-iframe {
    width: 100% !important;
    height: 100% !important;
    margin-bottom: 0 !important;
    border-radius: 0 !important;
  }
  
  .chatbot-fullscreen #chatbot-toggle {
    display: none !important;
  }
</style>

<div id="chatbot-container">
  <button id="chatbot-maximize" onclick="toggleFullscreen()" title="Maximizează">🗖</button>
  <iframe id="chatbot-iframe" src="http://localhost:8000/chat-ui"></iframe>
  <button id="chatbot-toggle" onclick="toggleChatbot()">💬</button>
</div>

<script>
  function toggleChatbot() {
    const container = document.getElementById('chatbot-container');
    const btn = document.getElementById('chatbot-toggle');
    const maxBtn = document.getElementById('chatbot-maximize');
    
    container.classList.toggle('chatbot-open');
    
    if (container.classList.contains('chatbot-open')) {
      btn.innerHTML = '❌'; 
    } else {
      btn.innerHTML = '💬'; 
      container.classList.remove('chatbot-fullscreen');
      maxBtn.innerHTML = '🗖';
      maxBtn.title = 'Maximizează';
    }
  }

  function toggleFullscreen() {
    const container = document.getElementById('chatbot-container');
    const maxBtn = document.getElementById('chatbot-maximize');
    
    container.classList.toggle('chatbot-fullscreen');
    
    if (container.classList.contains('chatbot-fullscreen')) {
      maxBtn.innerHTML = '🗗'; 
      maxBtn.title = 'Micșorează';
    } else {
      maxBtn.innerHTML = '🗖'; 
      maxBtn.title = 'Maximizează';
    }
  }
</script>
```

---

## 💡 Oprirea și Resetarea Sistemului

Pentru a opri aplicația:
```bash
docker compose down
```

Pentru a reseta complet sistemul (ștergerea bazei de date și a memoriei AI):
```bash
docker compose down -v
# Sterge manual folderul chroma_db daca vrei resetare la zero
```