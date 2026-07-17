                                        USER
                                          │
                                          ▼
                         ┌────────────────────────────────┐
                         │     Next.js Frontend (UI)      │
                         │────────────────────────────────│
                         │ • Chat Interface               │
                         │ • Conversation History         │
                         │ • Upload Notes                 │
                         │ • Quick Actions                │
                         │ • AI Settings                 │
                         │ • AI Inspector                │
                         │ • Source Citations            │
                         └────────────────────────────────┘
                                          │
                                   REST API Request
                                          │
                                          ▼
                        ┌─────────────────────────────────┐
                        │        FastAPI Backend          │
                        └─────────────────────────────────┘
                                          │
                                          ▼
                        ┌─────────────────────────────────┐
                        │         ChatService             │
                        │      (Main Orchestrator)        │
                        └─────────────────────────────────┘
                                          │
                        ┌─────────────────┴─────────────────┐
                        ▼                                   ▼
              ┌────────────────────┐             ┌────────────────────┐
              │    Intent Router   │             │ Conversation Store │
              │────────────────────│             │────────────────────│
              │ institutional_faq  │             │ Chat History       │
              │ personal_notes     │             │ Session Metadata   │
              │ escalate           │             └────────────────────┘
              │ out_of_scope       │
              └────────────────────┘
                        │
                        ▼
               ┌─────────────────────┐
               │    Safety Layer     │
               └─────────────────────┘
                        │
          ┌─────────────┴─────────────┐
          │                           │
     Safe Request              Unsafe Request
          │                           │
          ▼                           ▼
 ┌────────────────────┐      ┌──────────────────────┐
 │ Knowledge Routing  │      │ Escalation Manager   │
 └────────────────────┘      └──────────────────────┘
          │                           │
          │                    Ticket Logging
          │                           │
          ▼                           ▼
 ┌────────────────────────────────────────────────────┐
 │              Knowledge Sources                     │
 ├──────────────────────┬─────────────────────────────┤
 │ Institutional KB     │ Session KB                 │
 │ (Persistent FAISS)   │ (Temporary FAISS)          │
 │ Admissions           │ Uploaded PDF              │
 │ Fees                 │ DOCX                      │
 │ Hostel               │ TXT                       │
 │ Scholarships         │                           │
 │ Library              │                           │
 └──────────────┬───────┴──────────────┬────────────┘
                │                      │
                ▼                      ▼
          FAISS Retrieval        FAISS Retrieval
                │                      │
                └──────────┬───────────┘
                           ▼
                 ┌──────────────────────┐
                 │   Context Builder    │
                 └──────────────────────┘
                           │
                           ▼
              ┌────────────────────────────┐
              │ Hybrid Knowledge Mode      │
              ├────────────────────────────┤
              │ Grounded (RAG)             │
              │ General AI                 │
              │ No Official Information    │
              └────────────────────────────┘
                           │
                           ▼
                 ┌──────────────────────┐
                 │     LLM Service      │
                 └──────────────────────┘
                           │
                 ┌─────────┴──────────┐
                 ▼                    ▼
         ┌────────────────┐   ┌──────────────────┐
         │ Gemini API     │   │ LM Studio Local  │
         │ (Cloud)        │   │ (OpenAI API)     │
         └────────────────┘   └──────────────────┘
                           │
                           ▼
                ┌────────────────────────┐
                │ Citation Builder       │
                │ + Response Formatter   │
                └────────────────────────┘
                           │
                           ▼
                 Structured JSON Response
                           │
                           ▼
                    Next.js Frontend