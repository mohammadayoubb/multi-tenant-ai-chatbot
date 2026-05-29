File
What naser did
app/agent/router.py
Built/updated classifier-first router with fallback rules. Routes messages to blocked, rag_search, capture_lead, escalate, or agent. Later adapted it to support both simple config and Vault config.
app/agent/agent.py
Improved bounded agent scaffold. Added max iterations, token budget, strict tool allowlist, multi-tool planning, and memory budget counting.
app/agent/tools.py
Improved the three allowed tools: rag_search, capture_lead, escalate. Added safer input cleaning, top-k clamp, lead redaction, and structured outputs.
app/rag/retriever.py
Improved tenant-filtered RAG retrieval. Added safer chunking, explicit tenant filtering, lexical scoring, source metadata, and top-k limits.
app/rag/ingest.py
Improved CMS chunk preparation for future embeddings/pgvector. Added stable chunk IDs, source metadata, content hash, and timestamps.
app/infra/cache.py
Implemented/improved Redis session memory with key format session:{tenant_id}:{session_id}, TTL, redaction, safe Redis fallback, and config compatibility.
app/services/chat_service.py
Connected the full chat flow: memory → router → workflow/agent → tools → memory → response. Also redacts assistant response before memory storage.
app/prompts/system_prompt.md
Strengthened system prompt rules for tenant isolation, tool policy, prompt secrecy, escalation, and runtime tenant persona inject

evals/agent_tool_selection_cases.json
Golden set for tool/route selection: FAQ, human handoff, lead capture, spam, and mixed agent cases.
tests/evals/test_agent_tool_selection.py
Test that checks router route and agent tool plan against the golden set.
evals/rag_cases.json
Golden set for RAG retrieval, including tenant-isolation case.
tests/evals/test_rag_retrieval.py
Test that checks RAG source selection and expected terms.
evals/section_b_report.py
Small report script showing Agent/tool selection: 10/10 and RAG retrieval: 5/5.