from locust import HttpUser, task, between
import random

class ChatbotUser(HttpUser):
    # Timpul de asteptare (citire) al unui utilizator intre 2 intrebari (intre 2 si 5 secunde)
    wait_time = between(2.0, 5.0)

    # Lista de intrebari hibride (Reguli fixe + RAG)
    queries = [
        "Care este numarul de telefon de la secretariat?",
        "Care este adresa facultatii?",
        "Care este programul secretariatului?",
        "Cum se calculeaza cu exactitate media de admitere daca am dat bacul la informatica?",
        "Ce documente medicale sunt necesare pentru dosarul de inscriere?",
        "Care sunt taxele de scolarizare pentru anul acesta si cum le pot plati?",
        "Ce se intampla daca nu confirm locul la timp dupa afisarea rezultatelor?"
    ]

    @task
    def ask_question(self):
        # Alege o intrebare la intamplare
        question = random.choice(self.queries)
        
        # Trimite cererea POST catre endpoint-ul de chat
        self.client.post(
            "/chat", 
            json={"message": question},
            name="/chat [Hibrid]" # Numele sub care va aparea in grafice
        )

    def on_start(self):
        """Se executa cand un utilizator simulat 'intra' pe site"""
        self.client.get("/")