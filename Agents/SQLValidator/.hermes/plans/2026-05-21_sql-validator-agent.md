# SQL Validator Agent - Implementation Plan

## Goal
Build a complete SQL Validator agent that:
- Validates SQL against row-level and column-level security (RLS/CLS) rules
- Uses Groq LLM for validation and reasoning
- Generates synthetic data across domains/subdomains
- Has clear persona boundaries (what's given vs not given)
- Handles date column constraints

## Architecture

```
Groq Agent/
├── persona.md              # Agent persona + role boundaries
├── config.yaml             # Configuration (Groq API, RLS/CLS rules)
├── agent.py                # Main agent orchestration
├── sql_validator.py        # SQL validation engine (RLS/CLS)
├── synthetic_data.py       # Synthetic data generator
├── groq_client.py          # Groq API client
├── schemas/
│   └── domain_schema.json  # Domain/subdomain structure
├── data/
│   └── (generated CSVs)
└── tests/
    └── test_validator.py   # Tests
```

## Persona / Role Boundary

### What is Given (within boundary):
- SQL query to validate
- User context (who is executing)
- Domain/subdomain metadata
- RLS/CLS rules (who can see what rows/columns)
- Date column constraints

### What is NOT Given (outside boundary):
- The underlying database itself (works on schema + rules)
- User authentication (assumes user identity is provided)
- Query execution (validates, doesn't run)
- Data modification (read-only validation)

## Step-by-Step

1. Create project structure
2. Define persona.md (agent boundaries, tone)
3. Build config.yaml (Groq API key, RLS/CLS rules, domains)
4. Define domain/subdomain schema
5. Build synthetic_data.py - generates realistic data per domain
6. Build sql_validator.py - RLS/CLS enforcement engine
7. Build groq_client.py - Groq LLM integration
8. Build agent.py - orchestrator
9. Add tests
10. Add README

## Files to Create
- persona.md
- config.yaml
- agent.py
- sql_validator.py
- synthetic_data.py
- groq_client.py
- schemas/domain_schema.json
- tests/test_validator.py
- README.md
- .env.example
