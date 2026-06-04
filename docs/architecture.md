# Architecture

Three tiers: a React frontend, a FastAPI backend, and Supabase (Postgres +
pgvector, Auth, Storage). NVIDIA NIM serves both the chat model and the
embedding model over an OpenAI-compatible API.

```mermaid
flowchart TB
    subgraph client["React + Vite frontend"]
        UI["Auth · Document sidebar · Chat + SSE · Citation panel"]
    end

    subgraph api["FastAPI backend"]
        BE["JWT verify · Ingest · Retrieve · Stream chat"]
    end

    subgraph supabase["Supabase"]
        AUTH["Auth"]
        STORE["Storage — raw files"]
        DB[("Postgres + pgvector<br/>documents · chunks (vector, tsvector)<br/>conversations · messages<br/>— all RLS-scoped to auth.uid()")]
    end

    NIM["NVIDIA NIM<br/>Nemotron (chat) + nv-embedqa-e5 (embeddings)<br/>OpenAI-compatible"]

    UI -- "HTTPS + Bearer JWT" --> BE
    BE -- "SSE (text/event-stream)" --> UI
    UI -- "supabase-js (auth only)" --> AUTH
    BE -- "service-role" --> STORE
    BE -- "service-role" --> DB
    BE -- "embeddings + chat" --> NIM
```

The frontend talks to Supabase Auth directly (login only) and to the backend
for everything else. The backend is the only thing that touches the database
and storage, using a service-role key — so every query carries an explicit
`user_id` filter derived from the verified JWT. That filter is the tenant
boundary.

## Uploading a document

```mermaid
sequenceDiagram
    participant B as Browser
    participant API as FastAPI
    participant ST as Storage
    participant DB as Postgres
    participant NIM as NVIDIA NIM

    B->>API: POST /documents (multipart + JWT)
    API->>API: verify JWT
    API->>ST: upload bytes → <user_id>/<uuid>.ext
    API->>DB: insert documents row (status=pending)
    Note over API: schedule ingest_document as BackgroundTask
    API-->>B: 200 OK (document row, status=pending)
    API->>ST: download bytes
    API->>API: parse (pypdf) → token-aware, page-bounded chunking
    API->>NIM: batch embed chunks (input_type=passage)
    API->>DB: INSERT chunks (vector(1024) + generated tsvector)
    API->>DB: status → ready (or failed + error)
    loop every 2s while in flight
        B->>API: GET /documents (poll status)
    end
```

## Chatting

```mermaid
sequenceDiagram
    participant B as Browser
    participant API as FastAPI
    participant DB as Postgres
    participant NIM as NVIDIA NIM

    B->>API: POST /chat (JSON + JWT)
    API->>DB: persist user message
    API->>NIM: embed question (input_type=query)
    API->>DB: match_chunks RPC — vector + lexical, fused via RRF (k=60)
    DB-->>API: top-k chunks + filename/page metadata
    API->>API: build numbered context blocks + messages
    API-->>B: SSE meta event (citation index → chips appear)
    API->>NIM: stream chat completion
    NIM-->>API: token stream
    API-->>B: SSE token events
    API->>DB: persist assistant message (citations jsonb + per-stage latencies)
```
