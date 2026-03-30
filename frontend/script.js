/* LOGICA PENTRU CHAT */

async function sendMessage() {
    const chatInput = document.getElementById("chat-input");
    const text = chatInput.value.trim();
    if (!text) return;

    appendMessage(text, "user-msg");
    chatInput.value = "";

    const loadingId = appendMessage("Ma gandesc...", "bot-msg");

    try {
        const response = await fetch("http://127.0.0.1:8000/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text })
        });

        const data = await response.json();
        document.getElementById(loadingId).remove();
        
        let formattedAnswer = data.answer.replace(/\n/g, "<br>");
        let sourceHtml = `<span class="source-tag">Sursa: ${data.source}</span>`;
        
        let feedbackHtml = "";
        if (data.conversation_id) {
            // Generam 5 butoane cu stelute
            feedbackHtml = `
                <div class="feedback-container" id="feedback-${data.conversation_id}">
                    <button class="star-btn" onclick="sendFeedback(${data.conversation_id}, 1, this)" title="1 Stea">⭐</button>
                    <button class="star-btn" onclick="sendFeedback(${data.conversation_id}, 2, this)" title="2 Stele">⭐</button>
                    <button class="star-btn" onclick="sendFeedback(${data.conversation_id}, 3, this)" title="3 Stele">⭐</button>
                    <button class="star-btn" onclick="sendFeedback(${data.conversation_id}, 4, this)" title="4 Stele">⭐</button>
                    <button class="star-btn" onclick="sendFeedback(${data.conversation_id}, 5, this)" title="5 Stele">⭐</button>
                </div>
            `;
        }
        appendMessage(formattedAnswer + sourceHtml + feedbackHtml, "bot-msg", true);

    } catch (error) {
        document.getElementById(loadingId).remove();
        appendMessage("Eroare de conexiune cu serverul.", "bot-msg");
    }
}

function appendMessage(text, className, isHtml = false) {
    const chatMessages = document.getElementById("chat-messages");
    if (!chatMessages) return; 

    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${className}`;
    msgDiv.id = "msg-" + Date.now() + "-" + Math.floor(Math.random() * 10000);
    
    if (isHtml) msgDiv.innerHTML = text;
    else msgDiv.textContent = text;
    
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight; 
    return msgDiv.id;
}

function handleKeyPress(event) {
    if (event.key === "Enter") sendMessage();
}

async function sendFeedback(conversationId, rating, btnElement) {
    const container = btnElement.parentElement; 
    try {
        const response = await fetch(`/feedback/${conversationId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rating: rating })
        });
        if (response.ok) {
            container.innerHTML = "<span class='feedback-thanks'>Mulțumim pentru feedback! ✓</span>";
        }
    } catch (error) {
        console.error("Eroare la trimiterea feedback-ului:", error);
    }
}


/* LOGICA PENTRU DASHBOARD ADMIN  */

function showSection(id) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    event.target.classList.add('active');

    if(id === 'istoric') incarcaIstoric();
    if(id === 'reguli') incarcaReguli();
    if(id === 'surse') {
        incarcaSurse();
        incarcaDocumente();
    }
}

async function incarcaIstoric() {
    try {
        const res = await fetch('/logs');
        const data = await res.json();
        const tbody = document.getElementById('tabel-istoric');
        if (!tbody) return; // Protectie
        
        tbody.innerHTML = '';
        data.istoric_conversatii.forEach(row => {
            let afisareRating = "<span style='color: gray'>Fără notă</span>";
            if (row.rating !== null && row.rating > 0) {
                // Daca are nota, o afisam cu un galben auriu si bold
                afisareRating = `<span style='color: #d4af37; font-weight: bold;'>${row.rating} / 5 </span>`;
            }

            tbody.innerHTML += `<tr>
                <td>${row.data}</td>
                <td>${row.intrebare_utilizator}</td>
                <td>${row.raspuns_bot}</td>
                <td>${row.sursa}</td>
                <td style="text-align: center;">${afisareRating}</td>
            </tr>`;
        });
    } catch(e) { console.error("Eroare incarcare istoric", e); }
}

async function incarcaReguli() {
    const res = await fetch('/api/rules');
    const rules = await res.json();
    const tbody = document.getElementById('tabel-reguli');
    tbody.innerHTML = '';
    rules.forEach(r => {
        tbody.innerHTML += `<tr><td>${r.keyword}</td><td>${r.response}</td><td><button class="delete-btn" onclick="stergeRegula(${r.id})">Sterge</button></td></tr>`;
    });
}

async function adaugaRegula() {
    const keyword = document.getElementById('new-keyword').value;
    const response = document.getElementById('new-response').value;
    if (!keyword || !response) return alert("Completeaza ambele campuri!");
    await fetch('/api/rules', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ keyword: keyword, response: response }) });
    document.getElementById('new-keyword').value = '';
    document.getElementById('new-response').value = '';
    incarcaReguli();
}

async function stergeRegula(id) {
    if(!confirm("Sigur vrei sa stergi aceasta regula?")) return;
    await fetch(`/api/rules/${id}`, { method: 'DELETE' });
    incarcaReguli();
}

async function incarcaDocumente() {
    const res = await fetch('/api/documents');
    const docs = await res.json();
    const tbody = document.getElementById('tabel-documente');
    tbody.innerHTML = '';
    docs.forEach(d => {
        tbody.innerHTML += `<tr><td>${d.filename}</td><td><button class="delete-btn" onclick="stergeDocument('${d.filename}')">Sterge</button></td></tr>`;
    });
}

async function incarcaPDF() {
    const fileInput = document.getElementById('pdf-upload');
    if (fileInput.files.length === 0) return alert("Selecteaza un fisier PDF!");
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    try {
        const res = await fetch('/api/upload-pdf', { method: 'POST', body: formData });
        const data = await res.json();
        if(data.status === "success") {
            alert("Incarcat! Nu uita de butonul RE-INDEXARE!");
            fileInput.value = ""; incarcaDocumente(); 
        } else { alert("Eroare."); }
    } catch (e) { alert("Eroare de conexiune."); }
}

async function stergeDocument(filename) {
    if(!confirm(`Stergi fisierul ${filename}?`)) return;
    await fetch(`/api/documents/${filename}`, { method: 'DELETE' });
    incarcaDocumente(); 
}

async function incarcaSurse() {
    const res = await fetch('/api/weblinks');
    const links = await res.json();
    const tbody = document.getElementById('tabel-surse');
    tbody.innerHTML = '';
    links.forEach(l => {
        tbody.innerHTML += `<tr><td>${l.type}</td><td>${l.path}</td><td><button class="delete-btn" onclick="stergeLink(${l.id})">Sterge</button></td></tr>`;
    });
}

async function adaugaLink() {
    const path = document.getElementById('new-link').value;
    if (!path) return alert("Introdu un link!");
    await fetch('/api/weblinks', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ path: path }) });
    document.getElementById('new-link').value = '';
    incarcaSurse();
}

async function stergeLink(id) {
    if(!confirm("Stergi acest link?")) return;
    await fetch(`/api/weblinks/${id}`, { method: 'DELETE' });
    incarcaSurse();
}

async function reindexeazaAI() {
    const statusText = document.getElementById('reindex-status');
    statusText.innerText = "Se reindexeaza... (10-30s)";
    statusText.style.color = "orange";
    try {
        const res = await fetch('/api/reindex', { method: 'POST' });
        const data = await res.json();
        
        if (!res.ok) {
            throw new Error(data.detail || "Eroare necunoscuta pe server");
        }
        
        statusText.innerText = data.status;
        statusText.style.color = "green";
    } catch (e) {
        statusText.innerText = "Eroare la re-indexare: " + e.message;
        statusText.style.color = "red";
    }
}


// INITIALIZARE AUTOMATA LA INCARCAREA PAGINII
document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("tabel-istoric")) {
        incarcaIstoric();
    }
});