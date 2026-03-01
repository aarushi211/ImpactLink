# 📊 Grant Graph: AI-Driven Strategic Funding Matcher
Grant Graph is a high-precision RAG (Retrieval-Augmented Generation) pipeline designed to help NGOs find and win the best-fit grants. Unlike basic keyword search tools, Grant Graph uses a Two-Stage Re-Ranking architecture and Semantic Chunking to ensure that logical eligibility—not just word similarity—drives the results.

## 🚀 Key Features
- **Semantic Proposal Parsing:** Uses `SentenceTransformer` to break long PDF proposals into "semantic chapters," ensuring the AI captures the mission from the intro and the budget from the appendix.
- **Two-Stage Re-Ranker:** * Stage 1: High-speed vector retrieval using ChromaDB and all-MiniLM-L6-v2.
    - Stage 2: Logical "Deep Reasoner" re-ranking using `Groq (Llama 3.1 8B)` to verify geographic and mission eligibility.
- **Privacy-First Architecture:** Designed to run with local LLMs (Ollama) or high-speed cloud inference (Groq) depending on the environment.

## 🛠️ Tech Stack
|Category | Tools|
|---------|-------|
|LLM Inference | Groq (Llama 3.1 8B / 3.3 70B), Ollama|
|Vector Database| ChromaDB|
|Embeddings | Hugging Face `all-MiniLM-L6-v2`|
|Orchestration | LangChain, Pydantic (Structured Output)|
|Backend | FastAPI (Python 3.12) |
|Frontend | Next.js 15+, Tailwind CSS |

## 📦 Installation & Setup
**1. Clone the repository:**
```
git clone https://github.com/aarushi211/grant-graph.git
cd grant-graph
```

**2. Set up your environment:**
Create a `.env` file in the root directory:
```
GROQ_API_KEY=your_groq_key_here
USE_GROQ=True
LOCAL_LLM_MODEL=llama3
```

**3. Install dependencies:**
```
pip install -r requirements.txt
```

**4. Run the Backend:**
```
python main.py
```

## 🧠 The Pipeline Architecture
1. Ingestion: The NGO uploads a PDF.
2. Semantic Split: The LocalEmbedder identifies shifts in meaning to create 3-4 high-relevance chunks.
3. Feature Extraction: An LLM extracts a structured ProposalFeatures object.
4. Recall: ChromaDB retrieves the top 20 candidate grants based on vector distance.
5. Precision Re-Ranking: The Re-Ranker Agent evaluates those 20 candidates against the NGO's specific geographic and cause-area constraints, returning the Top 5.