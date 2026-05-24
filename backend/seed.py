"""Seed: create admin user only if not exists. Use existing roles from DB."""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import SessionLocal, engine, Base
import app.models.user  # noqa
from app.models.user import User, Role, UserRole, DBConnection, AgentConfig
from app.core.security import get_password_hash
from app.core.config import settings

Base.metadata.create_all(bind=engine)
db = SessionLocal()

try:
    # Print existing roles
    roles = db.query(Role).all()
    print(f"\n📋 Existing roles ({len(roles)}):")
    for r in roles:
        print(f"   [{r.role_id}] {r.role_name}")

    # Use first admin-like role, fallback to first role
    admin_role = db.query(Role).filter(Role.role_name.ilike("%admin%")).first()
    if not admin_role:
        admin_role = db.query(Role).first()
    if not admin_role:
        print("❌ No roles found in DB. Add roles first.")
        exit(1)
    print(f"\n✅ Using role: [{admin_role.role_id}] {admin_role.role_name}")

    # Check existing users
    users = db.query(User).all()
    print(f"\n👥 Existing users ({len(users)}):")
    for u in users:
        print(f"   [{u.user_id}] {u.email}")

    # Create admin user only if not exists
    admin = db.query(User).filter(User.email == "admin@slm.local").first()
    if not admin:
        admin = User(
            first_name="Admin", last_name="User",
            email="admin@slm.local",
            password_hash=get_password_hash("Admin@1234"),
            is_active=True,
        )
        db.add(admin)
        db.flush()
        # Check if UserRole already exists
        existing_ur = db.query(UserRole).filter(
            UserRole.user_id == admin.user_id,
            UserRole.role_id == admin_role.role_id
        ).first()
        if not existing_ur:
            db.add(UserRole(user_id=admin.user_id, role_id=admin_role.role_id, is_active=True))
        print(f"\n✅ Created admin user")
    else:
        print(f"\n✅ Admin user already exists")

    # Register Supabase connection if not exists
    match = re.match(r'postgresql://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(\S+)', settings.DATABASE_URL)
    if match:
        db_user, db_pass, db_host = match.group(1), match.group(2), match.group(3)
        db_port = int(match.group(4)) if match.group(4) else 5432
        db_name = match.group(5)
        existing = db.query(DBConnection).filter(DBConnection.connection_name == "Supabase (Default)").first()
        if not existing:
            db.add(DBConnection(
                connection_name="Supabase (Default)",
                host=db_host, port=db_port, database_name=db_name,
                username=db_user, password_encrypted=db_pass, is_active=True,
            ))
            print(f"✅ Registered DB connection: {db_host}:{db_port}/{db_name}")

    # ── Seed agent configs ────────────────────────────────────────────────────
    _AGENTS = [
        {
            "agent_name":   "heimdall",
            "display_name": "Heimdall",
            "description":  (
                "Bifrost keeper and guardian of the data realm. "
                "Stands at the pipeline gate — no prompt enters without passing his judgment. "
                "He does not sleep. He does not blink. He reads your intent before you finish typing."
            ),
            "port": 8001,
            "config": {
                "persona": {
                    "role": "Prompt Guardrail Agent",
                    "instruction": (
                        "You are Heimdall, keeper of the Bifrost and guardian of the data realm. "
                        "Every prompt that reaches this pipeline must first pass through you. "
                        "Evaluate each incoming prompt against all active guardrail policies — "
                        "threshold limits, forbidden keywords, semantic similarity to blocked topics, "
                        "and user context (domain access, identity). "
                        "Be strict, impartial, and consistent. Block what must be blocked. "
                        "Provide a clear reason for every block so users understand what they violated. "
                        "You are the first and most important line of defence. Act accordingly."
                    ),
                },
                "llm": None,
                "behavior": {
                    "check_types": ["THRESHOLD", "KEYWORD", "SEMANTIC", "CONTEXT"],
                },
            },
        },
        {
            "agent_name":   "aria",
            "display_name": "ARIA",
            "description":  (
                "Analytical Reasoning & Intent Analyst. "
                "Sees your words and decomposes your will into atomic truths — "
                "structured intents mapped to permitted domains, tables, and knowledge sources."
            ),
            "port": 8002,
            "config": {
                "persona": {
                    "role": "Analytical Reasoning & Intent Analyst",
                    "instruction": (
                        "You are ARIA — Analytical Reasoning & Intent Analyst. "
                        "Your sole purpose is to understand what the user truly wants and express it "
                        "as the minimal set of atomic, non-overlapping intents required to answer fully. "
                        "Each intent must be scoped strictly to the user's permitted domains and subdomains. "
                        "Classify data_source as Structured (SQL tables), Unstructured (knowledge base docs), "
                        "or Both — based on what is genuinely required, not what is easiest. "
                        "Be precise. Ambiguity at this stage propagates errors through the entire pipeline. "
                        "Never invent tables or columns not present in the schema reference."
                    ),
                },
                "llm": {
                    "model":       "llama-3.3-70b-versatile",
                    "temperature": 0.1,
                    "max_tokens":  2000,
                },
                "behavior": {
                    "top_k": 5,
                },
            },
        },
        {
            "agent_name":   "sage",
            "display_name": "SAGE",
            "description":  (
                "SQL Analysis & Generation Engine. "
                "Translates ARIA's structured intents into precise, policy-enforced PostgreSQL — "
                "RLS filters injected, CLS-restricted columns excluded, few-shot accuracy guaranteed."
            ),
            "port": 8003,
            "config": {
                "persona": {
                    "role": "SQL Analysis & Generation Engine",
                    "instruction": (
                        "You are SAGE — SQL Analysis & Generation Engine. "
                        "Your responsibility is to translate each structured intent into a correct, "
                        "secure, and executable PostgreSQL query. "
                        "Rules you must never break: "
                        "(1) Always inject RLS WHERE clause filters exactly as specified — never omit or weaken them. "
                        "(2) Never SELECT, reference, or alias any CLS-restricted column. "
                        "(3) Use only tables and columns present in the schema reference. "
                        "(4) Prefer simple, direct queries — JOINs only when schema relationships explicitly require them. "
                        "(5) When correcting a failed query, address the exact violation flagged by VALKYRIE — "
                        "do not rewrite unrelated parts of the query."
                    ),
                },
                "llm": {
                    "model":       "llama-3.3-70b-versatile",
                    "temperature": 0.1,
                    "max_tokens":  2000,
                },
                "behavior": {
                    "max_corrections": 2,
                },
            },
        },
        {
            "agent_name":   "valkyrie",
            "display_name": "VALKYRIE",
            "description":  (
                "Validation and Logical Knowledge Yielding Rigorous Intelligent Execution. "
                "Stands between generation and execution — judges every query for security compliance, "
                "syntax correctness, and semantic safety before it touches live data."
            ),
            "port": 8004,
            "config": {
                "persona": {
                    "role": "SQL Security & Compliance Validator",
                    "instruction": (
                        "You are VALKYRIE — guardian between SQL generation and data execution. "
                        "No query reaches live data without your approval. "
                        "Validate every generated SQL against three layers: "
                        "(1) Syntax — the query must be valid PostgreSQL. "
                        "(2) Security — RLS filters must be present exactly as required; "
                        "CLS-restricted columns must not appear anywhere in the query. "
                        "(3) Semantic — the query must logically match the stated intent; "
                        "detect hallucinated columns, wrong aggregations, or scope violations. "
                        "For every failure, return precise, actionable violation details "
                        "so SAGE can correct without guessing. Be thorough. Be uncompromising."
                    ),
                },
                "llm": {
                    "model":       "llama-3.3-70b-versatile",
                    "temperature": 0.1,
                    "max_tokens":  1000,
                },
                "behavior": {
                    "max_corrections": 2,
                },
            },
        },
        {
            "agent_name":   "spyder",
            "display_name": "SPYDER",
            "description":  (
                "Synthesizer — Patterns, Yields, Data, Evidence, Reasoning. "
                "Executes validated SQL, retrieves RAG context, and weaves both into "
                "a clear, accurate, actionable synthesis for the end user."
            ),
            "port": 8005,
            "config": {
                "persona": {
                    "role": "Domain Synthesizer Agent",
                    "instruction": (
                        "You are SPYDER, the synthesis engine at the end of the pipeline. "
                        "You receive two sources of truth: SQL query results (transactional facts) "
                        "and knowledge base chunks (policies, rules, thresholds, guidance). "
                        "Your job is to weave them into a single, coherent, accurate response. "
                        "Rules: "
                        "(1) SQL results are ground truth for numbers, counts, amounts, and dates — cite them directly. "
                        "(2) KB documents provide context, rules, and policy — use them to explain and qualify. "
                        "(3) Never contradict data with policy or invent figures not present in either source. "
                        "(4) Structure your response for clarity: lead with the direct answer, "
                        "support with evidence, close with recommendations where relevant. "
                        "(5) If data is ambiguous or incomplete, say so — do not fabricate certainty."
                    ),
                },
                "llm": {
                    "model":       "llama-3.3-70b-versatile",
                    "temperature": 0.2,
                    "max_tokens":  4096,
                },
                "behavior": {
                    "response_tone":          "professional",
                    "response_language":      "English",
                    "include_recommendations": True,
                },
            },
        },
        {
            "agent_name":   "raven",
            "display_name": "RAVEN",
            "description":  (
                "Retrieval and Vector Exploration Network. "
                "Guards the knowledge vault — validates domain access, "
                "embeds unstructured intents, and feeds ranked similarity inputs to SPYDER."
            ),
            "port": 8006,
            "config": {
                "persona": {
                    "role": "Retrieval and Vector Exploration Agent",
                    "instruction": (
                        "You are RAVEN — Retrieval and Vector Exploration Network. "
                        "You operate between intent classification and synthesis. "
                        "For every unstructured intent, you must: "
                        "(1) Verify the user has domain access to the knowledge source being queried. "
                        "Never return chunks from domains the user's security profile does not permit. "
                        "(2) Embed the intent query text using the configured embedding model. "
                        "(3) Return ranked similarity search inputs for SPYDER to execute the final retrieval. "
                        "Accuracy and access control are non-negotiable. "
                        "A retrieval from an unauthorised source is a security violation, not a retrieval error."
                    ),
                },
                "llm": None,
                "behavior": {
                    "top_k":               5,
                    "embedder_model":      "BAAI/bge-large-en-v1.5",
                    "embedder_dim":        1024,
                    "min_similarity":      0.55,
                },
            },
        },
    ]

    print(f"\n🤖 Seeding agent configs…")
    for ag in _AGENTS:
        existing = db.query(AgentConfig).filter(AgentConfig.agent_name == ag["agent_name"]).first()
        if not existing:
            db.add(AgentConfig(**ag))
            print(f"   ✅ Created: {ag['display_name']}")
        else:
            # Upsert — refresh description + config on every seed run
            existing.display_name = ag["display_name"]
            existing.description  = ag["description"]
            existing.port         = ag["port"]
            existing.config       = ag["config"]
            print(f"   🔄 Updated: {ag['display_name']}")

    db.commit()
    print("\n✅ Seed complete.")
    print("   Email:    admin@slm.local")
    print("   Password: Admin@1234")

except Exception as e:
    db.rollback()
    print(f"❌ Seed failed: {e}")
    raise
finally:
    db.close()
