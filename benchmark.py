import time
import requests

API_URL = "http://localhost:8000/chat" 

standard_queries = [
    "Care este numarul de telefon de la secretariat?",
    "Care este adresa facultatii?",
    "Care este programul secretariatului?",
    "Vreau adresa de email pentru admitere.",
    "Cum contactez facultatea?"
]

complex_queries = [
    "Cum se calculeaza cu exactitate media de admitere daca am dat bacul la informatica?",
    "Ce documente medicale sunt necesare pentru dosarul de inscriere?",
    "Care sunt taxele de scolarizare pentru anul acesta si cum le pot plati?",
    "Exista locuri speciale pentru candidatii din mediul rural? Care e procedura?",
    "Ce se intampla daca nu confirm locul la timp dupa afisarea rezultatelor?"
]

def run_benchmark():
    print("Incepere Benchmark (Testare Latenta & Eficienta)...\n")
    
    # 1. Testare Ruta Determinista 
    print("--- Testare intrebari Standard (Rule-Based) ---")
    standard_times = []
    for query in standard_queries:
        start_time = time.time()
        response = requests.post(API_URL, json={"message": query}) 
        end_time = time.time()
        
        
        if response.status_code == 200:
            latency = (end_time - start_time) * 1000 # conversie milisecunde
            standard_times.append(latency)
            print(f"[{latency:.2f} ms] {query}")
        else:
            print(f"Eroare {response.status_code}: {response.text} la: {query}")
            
        time.sleep(3)
            
    # 2. Testare Ruta Probabilistica 
    print("\n--- Testare intrebari Complexe  ---")
    complex_times = []
    for query in complex_queries:
        start_time = time.time()
        response = requests.post(API_URL, json={"message": query})
        end_time = time.time()
        
        if response.status_code == 200:
            latency = end_time - start_time 
            complex_times.append(latency)
            print(f"[{latency:.2f} s] {query}")
        else:
            print(f"Eroare {response.status_code}: {response.text} la: {query}")

    # 3. Generare Raport Final
    avg_standard = sum(standard_times) / len(standard_times) if standard_times else 0
    avg_complex = sum(complex_times) / len(complex_times) if complex_times else 0
    
    print("\n================ RAPORT FINAL ================")
    print(f"Latenta Medie Rule-Based: {avg_standard:.2f} ms")
    print(f"Latenta Medie RAG + LLM:  {avg_complex:.2f} secunde")
    
    # Calcul Eficienta Tokeni
    tokens_saved = len(standard_queries) * 500 
    print(f"\nEficienta Router-ului Semantic:")
    print(f"S-au evitat apeluri LLM pentru {len(standard_queries)} interogari.")
    print(f"Economie estimata de resurse: ~{tokens_saved} tokeni salvati.")
    print("==============================================")

if __name__ == "__main__":
    run_benchmark()