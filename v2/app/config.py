"""Phase 1 configuration: deterministic defaults and versioned prompts."""

import os
from dotenv import load_dotenv

load_dotenv()

# LLM
GROQ_MODEL_ID = os.getenv("GROQ_MODEL_ID", "llama-3.1-8b-instant")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))

# Prompt versions (audit / reproducibility)
PROMPT_VERSION_PLANNER = os.getenv("PROMPT_VERSION_PLANNER", "planner-v2.0")
PROMPT_VERSION_SQL = os.getenv("PROMPT_VERSION_SQL", "sql-v2.0")
PROMPT_VERSION_PYTHON = os.getenv("PROMPT_VERSION_PYTHON", "python-v1.0")
PROMPT_VERSION_INSIGHT = os.getenv("PROMPT_VERSION_INSIGHT", "insight-v2.0")

PROMPT_VERSIONS = {
    "planner": PROMPT_VERSION_PLANNER,
    "sql_generator": PROMPT_VERSION_SQL,
    "python_analyzer": PROMPT_VERSION_PYTHON,
    "insight_synthesizer": PROMPT_VERSION_INSIGHT,
}

# Pipeline guardrails
MAX_SQL_RETRIES = int(os.getenv("MAX_SQL_RETRIES", "3"))
SQL_ROW_LIMIT = int(os.getenv("SQL_ROW_LIMIT", "10"))
SQL_COMPLEXITY_MAX_JOINS = int(os.getenv("SQL_COMPLEXITY_MAX_JOINS", "6"))
DETERMINISTIC_MODE_DEFAULT = os.getenv("DETERMINISTIC_MODE", "true").lower() == "true"

# Multi-step orchestration (Option B)
MULTI_STEP_ENABLED = os.getenv("MULTI_STEP_ENABLED", "true").lower() == "true"
MAX_TARGETS = int(os.getenv("MAX_TARGETS", "5"))
MAX_SQL_RETRIES_PER_TARGET = int(os.getenv("MAX_SQL_RETRIES_PER_TARGET", "3"))

# RAG (PDF -> Pinecone + OpenAI embeddings; required for planner/SQL prompts)
KNOWLEDGE_SCHEMA_PDF = os.getenv(
    "KNOWLEDGE_SCHEMA_PDF",
    "app/knowledge/schema.pdf",
)
KNOWLEDGE_RULES_PDF = os.getenv(
    "KNOWLEDGE_RULES_PDF",
    "app/knowledge/business_logic.pdf",
)
KNOWLEDGE_VERSION = os.getenv("KNOWLEDGE_VERSION", "1.0.0")
PDF_CHUNK_MAX_CHARS = int(os.getenv("PDF_CHUNK_MAX_CHARS", "2000"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "8"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "erp-analyst")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "")

# strict_word_similarity match bands (0.0–1.0)
ENTITY_MATCH_EXCELLENT_MIN = float(os.getenv("ENTITY_MATCH_EXCELLENT_MIN", "0.8"))
ENTITY_MATCH_FAIR_MIN = float(os.getenv("ENTITY_MATCH_FAIR_MIN", "0.4"))
ENTITY_MATCH_AMBIGUITY_GAP = float(os.getenv("ENTITY_MATCH_AMBIGUITY_GAP", "0.05"))
ENTITY_MATCH_CANDIDATE_LIMIT = int(os.getenv("ENTITY_MATCH_CANDIDATE_LIMIT", "10"))
ENTITY_MATCH_SCORE_COLUMN = "match_score"

# API
API_VERSION = "2.6.0-entity-match-llm-extract"
