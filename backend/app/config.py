"""Runtime configuration. Everything is overridable by environment variable (or backend/.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

MERCHANT_CSV_PATH = Path(os.getenv("MERCHANT_CSV_PATH", ROOT_DIR / "structured_data" / "merchant_profiles_v3.csv"))
POS_CSV_PATH = Path(os.getenv("POS_CSV_PATH", ROOT_DIR / "structured_data" / "pos_daily_acquiring_v3.csv"))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BACKEND_DIR / 'rm_copilot.db').as_posix()}")
PRODUCTS_CSV_PATH = Path(os.getenv("PRODUCTS_CSV_PATH", ROOT_DIR / "structured_data" / "merchant_products_held_v2.csv"))
NTB_CSV_PATH = Path(os.getenv("NTB_CSV_PATH", ROOT_DIR / "structured_data" / "ntb_cross_sell_candidates.csv"))
QUALITY_REPORT_PATH = Path(os.getenv("QUALITY_REPORT_PATH", BACKEND_DIR / "data_quality_report.json"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435").strip().rstrip("/")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip()
# Ollama is local and does not require an API key. Set LLM_PROVIDER=anthropic to use the retained Anthropic path.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower() or "ollama"
# Previous OpenAI/Anthropic provider selection and defaults, retained for rollback:
# LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").strip().lower() or ("openai" if OPENAI_API_KEY else "anthropic")
# LLM_MODEL = os.getenv("LLM_MODEL", "").strip() or ("gpt-4o-mini" if LLM_PROVIDER == "openai" else "claude-opus-5-5")
LLM_MODEL = os.getenv("LLM_MODEL", "").strip() or ("qwen3:8b-rm" if LLM_PROVIDER == "ollama" else "claude-opus-5-5")
# Optional stronger model for the offline per-client suggestion batch (defaults to LLM_MODEL)
SUGGESTION_MODEL = os.getenv("SUGGESTION_MODEL", "").strip()
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "350" if LLM_PROVIDER == "ollama" else "1500"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120" if LLM_PROVIDER == "ollama" else "45"))
SUGGESTION_TIMEOUT = float(os.getenv("SUGGESTION_TIMEOUT", "180" if LLM_PROVIDER == "ollama" else "60"))
LLM_API_KEY = "ollama" if LLM_PROVIDER == "ollama" else (OPENAI_API_KEY if LLM_PROVIDER == "openai" else ANTHROPIC_API_KEY)
# Prompt sizing. The window is kept at OLLAMA_NUM_CTX for speed; the prompt is built to fit it (see prompt_budget.py).
PROMPT_TOKENS = int(os.getenv("PROMPT_TOKENS", str(OLLAMA_NUM_CTX)))
HISTORY_MAX_CHARS = int(os.getenv("HISTORY_MAX_CHARS", "4000"))      # older chat turns are dropped past this, newest kept
PORTFOLIO_ROW_LIMIT = int(os.getenv("PORTFOLIO_ROW_LIMIT", "8"))     # clients listed per portfolio question; counts cover all clients. 8 fits the reply limit
CHAT_CACHE_ENABLED =os.getenv("CHAT_CACHE_ENABLED", "1").strip() != "0"
CHAT_CACHE_PATH = Path(os.getenv("CHAT_CACHE_PATH", BACKEND_DIR / ".cache" / "chroma"))
CHAT_CACHE_TTL_SECONDS = int(os.getenv("CHAT_CACHE_TTL_SECONDS", "86400"))
CHAT_CACHE_MAX_ENTRIES = int(os.getenv("CHAT_CACHE_MAX_ENTRIES", "500"))
CHAT_CACHE_SEMANTIC_DISTANCE = float(os.getenv("CHAT_CACHE_SEMANTIC_DISTANCE", "0.22"))

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# Audit log (JSON Lines) and chat rate limit (requests per minute per client address; 0 disables)
AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", BACKEND_DIR / "audit_log.jsonl"))
AUDIT_LOG_ENABLED = os.getenv("AUDIT_LOG_ENABLED", "1").strip() != "0"
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))

# NeMo Guardrails: master switch, the two LLM-based rails (extra model calls; the deterministic rails always run), per-check timeout (s)
GUARDRAILS_ENABLED = os.getenv("GUARDRAILS_ENABLED", "1").strip() != "0"
GUARDRAILS_LLM_CHECKS = os.getenv("GUARDRAILS_LLM_CHECKS", "1").strip() != "0"
GUARDRAILS_TIMEOUT = float(os.getenv("GUARDRAILS_TIMEOUT", "150" if LLM_PROVIDER == "ollama" else "60"))

DISCLAIMER = "Synthetic demonstration data. Not real customer, bureau or compliance data."
