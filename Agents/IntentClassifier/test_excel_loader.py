from app import _load_excel_queries

with open(r"C:\gemma_ai_studio_intent_classifier_app\direct_testing\direct_testing_file.xlsx", "rb") as f:
    queries, q_col, sr_col = _load_excel_queries(f)

print(f"Query column  : {q_col}")
print(f"SR.No column  : {sr_col}")
print(f"Queries loaded: {len(queries)}")
print()
for q in queries[:5]:
    print(f"  SR {q['sr_no']:>2} | {q['query'][:80]}...")
