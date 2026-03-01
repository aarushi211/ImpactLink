
<<<<<<< HEAD
## 🚀 Key Features
- **Smart Grant Discovery:**: View and filter a curated database of global grants with real-time match scoring
- **AI Proposal Draft Assistant:** Generate high-quality first drafts of grant applications tailored specifically to the requirements of a selected funder
- **Interactive Budget Builder:** Integrated tools to structure project finances, ensuring alignment with grant limits and category requirements
- **NGO Dashboard:** A centralized "Mission Control" to track active applications, saved grants, and project drafts
- **Semantic Proposal Parsing:** Uses `SentenceTransformer` to break long PDF proposals into "semantic chapters," ensuring the AI captures the mission from the intro and the budget from the appendix
- **Two-Stage Re-Ranker:**
    - Stage 1 (Recall): High-speed vector retrieval using `ChromaDB` and `all-MiniLM-L6-v2` to find potential matches
    - Stage 2: A logical "Deep Reasoner" re-ranking agent using Groq (Llama 3.1 8B) to verify hard constraints like geographic and mission eligibility
- **Privacy-First Architecture:** Designed to run with local LLMs (Ollama) or high-speed cloud inference (Groq) depending on the sensitivity of the NGO's data
- **ImpactLink Frontend**: A modern, responsive dashboard built with Next.js to visualize match scores and funding insights.

## 🔴 The Problem
Small NGOs often lack dedicated grant-writing teams. They spend ~40% of their time manually filtering through 50+ page PDFs, only to find they are ineligible due to a single clause buried in the appendix. This "Information Overload" leads to a 70% rejection rate for grassroots organizations.

## 🟢 The Solution
Grant Graph is a high-precision RAG pipeline that automates the eligibility "Deep Reasoner." By using semantic chunking and a two-stage re-ranking architecture, it ensures that NGOs only spend time on grants they are logically qualified to win. It then assists in drafting and budgeting to turn a mission into a winning proposal in minutes.

## 🛠️ Tech Stack
|Category | Tools|
|---------|-------|
|LLM Inference | Groq (Llama 3.1 8B / 3.3 70B), Ollama|
|Vector Database| ChromaDB|
|Embeddings | Hugging Face `all-MiniLM-L6-v2`|
|Orchestration | LangChain, Pydantic (Structured Output)|
|Backend | FastAPI (Python 3.12) |
|Frontend | Next.js 15+, Tailwind CSS, Lucide React |

## 🛠️ Product Workflow
Grant Graph takes an NGO from "Idea" to "Submitted" in one seamless flow:
- **Upload & Analyze:** Upload an existing project proposal or concept note (PDF).
- **Match:** The AI extracts your mission and constraints to find the top 5 most compatible grants.
- **Refine:** Use the Budget Builder to align your costs with the specific grant's ceiling.
- **Draft:** Use the Draft Assistant to "remix" your original proposal into the specific format required by the grantor.
- **Track:** Manage all your historical and pending applications through the Grant Dashboard.


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

📁 Project Structure
- `/agents`: Logic for the Re-Ranker and Reasoning agents.
- `/services`: Core RAG logic and vector database management.
- `/impactlink-frontend`: Next.js web application.
- `graphql_server.py`: API layer for handling complex data queries.
- `load_vectors.py`: Script for ingesting and embedding grant datasets.

## 🗺️ Future Roadmap
While the core RAG pipeline and dashboard are functional, we envision Grant Graph evolving into a comprehensive ecosystem for non-profit success:
- **Multi-Agent Collaborative Drafting:** Implementing a "Critique Agent" that acts as a mock grant reviewer to score drafts and suggest improvements before submission.
- **Automatic Grant Scraping:** Integration with grants.gov and international NGO databases to provide real-time alerts for new funding opportunities.
- **Multi-Modal Ingestion:** Supporting image-to-text for scanning physical grant flyers or handwritten project notes from field workers.
- **Privacy-First Local Deployment:** Further optimizing the pipeline for quantized GGUF models to allow the entire suite to run offline on a standard laptop in areas with low internet connectivity.
- **Impact Reporting:** A module to help NGOs auto-generate progress reports for donors by pulling data from their internal project logs.

## 🏆 Hackathon Notes
Small NGOs often lack dedicated grant writers, putting them at a disadvantage against larger organizations. Grant Graph levels the playing field by providing professional-grade drafting and budgeting tools, allowing grassroots organizations to focus their energy where it belongs: on the mission.
=======
>>>>>>> d1f2bbd043276083d835d5527db5f99ffb881b13
