// ==========================================
// 1. SECURITATE SI AUTENTIFICARE (JWT)
// ==========================================

// Verificam daca utilizatorul are voie sa fie pe dashboard
if (window.location.pathname.includes("dashboard")) {
    const token = localStorage.getItem("admin_token");
    if (!token) {
        window.location.href = "/static/login.html";
    }
}

// Functie helper pentru a pune token-ul in header-ul cererilor
function getAuthHeaders(isJson = true) {
    const headers = {
        "Authorization": `Bearer ${localStorage.getItem("admin_token")}`
    };
    if (isJson) headers["Content-Type"] = "application/json";
    return headers;
}

// Functie pentru Login
async function doLogin() {
    const user = document.getElementById("username").value;
    const pass = document.getElementById("password").value;
    const errorMsg = document.getElementById("error-msg");
    
    const formData = new URLSearchParams();
    formData.append("username", user);
    formData.append("password", pass);

    try {
        const res = await fetch("/login", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData
        });

        if (res.ok) {
            const data = await res.json();
            localStorage.setItem("admin_token", data.access_token);
            window.location.href = "/dashboard"; // Ruta din FastAPI catre dashboard
        } else {
            errorMsg.innerText = "Utilizator sau parolă incorecte!";
        }
    } catch (e) {
        errorMsg.innerText = "Eroare de conexiune cu serverul.";
    }
}

function handleEnterLogin(event) {
    if (event.key === "Enter") doLogin();
}

// Functie pentru Logout
function logoutAdmin() {
    localStorage.removeItem("admin_token");
    window.location.href = "/static/login.html";
}


// ==========================================
// 2. LOGICA PENTRU CHAT (PUBLIC)
// ==========================================

async function sendMessage() {
    const chatInput = document.getElementById("chat-input");
    const text = chatInput.value.trim();
    if (!text) return;

    appendMessage(text, "user-msg");
    chatInput.value = "";

    const loadingId = appendMessage("Mă gândesc...", "bot-msg");

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text })
        });

        const data = await response.json();
        document.getElementById(loadingId).remove();
        
        let formattedAnswer = marked.parse(data.answer);
        let sourceHtml = `<span class="source-tag">Sursa: ${data.source}</span>`;
        
        let feedbackHtml = "";
        if (data.conversation_id) {
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


// ==========================================
// 3. LOGICA PENTRU DASHBOARD (ADMIN PROTEJAT)
// ==========================================

function showSection(id) {
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    event.target.classList.add('active');

    if(id === 'istoric') loadHistory();
    if(id === 'reguli') loadRules();
    if(id === 'surse') {
        loadSources();
        loadDocuments();
    }
}

async function loadHistory() {
    try {
        const res = await fetch('/logs', { headers: getAuthHeaders() });
        if (res.status === 401) return logoutAdmin();
        
        const data = await res.json();
        const tbody = document.getElementById('tabel-istoric');
        if (!tbody) return; 
        
        tbody.innerHTML = '';
        data.istoric_conversatii.forEach(row => {
            let displayRating = "<span style='color: gray'>-</span>";
            if (row.rating !== null && row.rating > 0) {
                displayRating = `<strong>${row.rating}/5</strong>`;
            }

            let displaySource = row.sursa;
            if (row.sursa === "rule-based") {
                displaySource = "<strong>Regulă Fixă</strong>";
            } else if (row.sursa.startsWith("ai-rag")) {
                let cleanName = row.sursa.replace("ai-rag (", "").replace(")", "");
                displaySource = `<strong>${cleanName}</strong>`;
            }

            tbody.innerHTML += `<tr>
                <td style="font-size: 0.9em; color: #555;">${row.data}</td>
                <td>${row.intrebare_utilizator}</td>
                <td>${row.raspuns_bot}</td>
                <td style="text-align: center;">${displaySource}</td>
                <td style="text-align: center;">${displayRating}</td>
            </tr>`;
        });
    } catch(e) { console.error("Error loading history:", e); }
}

async function loadRules() {
    const res = await fetch('/api/rules', { headers: getAuthHeaders() });
    if (res.status === 401) return logoutAdmin();
    const rules = await res.json();
    const tbody = document.getElementById('tabel-reguli');
    tbody.innerHTML = '';
    rules.forEach(r => {
        tbody.innerHTML += `<tr><td>${r.keyword}</td><td>${r.response}</td><td><button class="delete-btn" onclick="deleteRule(${r.id})">Sterge</button></td></tr>`;
    });
}

async function addRule() {
    const keyword = document.getElementById('new-keyword').value;
    const response = document.getElementById('new-response').value;
    if (!keyword || !response) return alert("Completeaza ambele campuri!");
    
    await fetch('/api/rules', { 
        method: 'POST', 
        headers: getAuthHeaders(), 
        body: JSON.stringify({ keyword: keyword, response: response }) 
    });
    
    document.getElementById('new-keyword').value = '';
    document.getElementById('new-response').value = '';
    loadRules();
}

async function deleteRule(id) {
    if(!confirm("Sigur vrei sa stergi aceasta regula?")) return;
    await fetch(`/api/rules/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
    loadRules();
}

async function loadDocuments() {
    const res = await fetch('/api/documents', { headers: getAuthHeaders() });
    if (res.status === 401) return logoutAdmin();
    const docs = await res.json();
    const tbody = document.getElementById('tabel-documente');
    tbody.innerHTML = '';
    docs.forEach(d => {
        tbody.innerHTML += `<tr><td>${d.filename}</td><td><button class="delete-btn" onclick="deleteDocument('${d.filename}')">Sterge</button></td></tr>`;
    });
}

async function uploadPDF() {
    const fileInput = document.getElementById('pdf-upload');
    if (fileInput.files.length === 0) return alert("Selecteaza un fisier PDF!");
    
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    
    try {
        const res = await fetch('/api/upload-pdf', { 
            method: 'POST', 
            headers: getAuthHeaders(false), // false = nu punem JSON content-type
            body: formData 
        });
        if (res.status === 401) return logoutAdmin();
        const data = await res.json();
        
        if(data.status === "success") {
            alert("Incarcat! Nu uita de butonul RE-INDEXARE!");
            fileInput.value = ""; 
            loadDocuments(); 
        } else { 
            alert("Eroare la incarcare."); 
        }
    } catch (e) { 
        alert("Eroare de conexiune."); 
    }
}

async function deleteDocument(filename) {
    if(!confirm(`Stergi fisierul ${filename}?`)) return;
    await fetch(`/api/documents/${filename}`, { method: 'DELETE', headers: getAuthHeaders() });
    loadDocuments(); 
}

async function loadSources() {
    const res = await fetch('/api/weblinks', { headers: getAuthHeaders() });
    if (res.status === 401) return logoutAdmin();
    const links = await res.json();
    const tbody = document.getElementById('tabel-surse');
    tbody.innerHTML = '';
    links.forEach(l => {
        tbody.innerHTML += `<tr><td>${l.type}</td><td>${l.path}</td><td><button class="delete-btn" onclick="deleteLink(${l.id})">Sterge</button></td></tr>`;
    });
}

async function addLink() {
    const path = document.getElementById('new-link').value;
    if (!path) return alert("Introdu un link!");
    
    await fetch('/api/weblinks', { 
        method: 'POST', 
        headers: getAuthHeaders(), 
        body: JSON.stringify({ path: path }) 
    });
    
    document.getElementById('new-link').value = '';
    loadSources();
}

async function deleteLink(id) {
    if(!confirm("Stergi acest link?")) return;
    await fetch(`/api/weblinks/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
    loadSources();
}

async function reindexAI() {
    const statusText = document.getElementById('reindex-status');
    statusText.innerText = "Se reindexeaza... (10-30s)";
    statusText.style.color = "orange";
    
    try {
        const res = await fetch('/api/reindex', { 
            method: 'POST',
            headers: getAuthHeaders(false) 
        });
        
        if (res.status === 401) return logoutAdmin();
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

// AUTO-INITIALIZE ON PAGE LOAD
document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("tabel-istoric")) {
        loadHistory();
    }
});