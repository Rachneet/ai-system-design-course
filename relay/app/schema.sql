-- pgvector lives in public so per-test and per-eval schemas can be dropped without dropping the extension.
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;

CREATE TABLE IF NOT EXISTS customers (
  id    text PRIMARY KEY,
  name  text NOT NULL,
  email text NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  id           int PRIMARY KEY,
  customer_id  text NOT NULL REFERENCES customers(id),
  status       text NOT NULL CHECK (status IN ('processing', 'shipped', 'delivered', 'cancelled')),
  total        numeric(10, 2) NOT NULL,
  items        jsonb NOT NULL,          -- [{sku, name, category, qty, price, used}]
  eta          date,
  delivered_at timestamptz
);

CREATE TABLE IF NOT EXISTS refunds (
  id         serial PRIMARY KEY,
  order_id   int NOT NULL UNIQUE REFERENCES orders(id),   -- one refund per order: retries are safe
  amount     numeric(10, 2) NOT NULL,
  reason     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approvals (
  id         serial PRIMARY KEY,
  order_id   int NOT NULL REFERENCES orders(id),
  amount     numeric(10, 2) NOT NULL,
  reason     text NOT NULL,
  status     text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'executed')),
  session_id uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS escalations (
  id          serial PRIMARY KEY,
  customer_id text NOT NULL,
  session_id  uuid,
  reason      text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
  id          uuid PRIMARY KEY,
  customer_id text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
  session_id uuid NOT NULL REFERENCES sessions(id),
  seq        int  NOT NULL,
  role       text NOT NULL CHECK (role IN ('user', 'assistant')),
  content    jsonb NOT NULL,   -- exact API content blocks, including tool_use and tool_result
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (session_id, seq)
);

CREATE TABLE IF NOT EXISTS memories (
  id             serial PRIMARY KEY,
  customer_id    text NOT NULL,
  fact           text NOT NULL,
  category       text NOT NULL,
  source_session uuid,
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (customer_id, fact)
);
CREATE INDEX IF NOT EXISTS memories_customer ON memories (customer_id, updated_at DESC);

-- ---- Lab 2: knowledge base ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
  doc_id       text PRIMARY KEY,           -- the source's own ID (file stem here)
  title        text NOT NULL,
  source_path  text NOT NULL,
  content_hash text NOT NULL,              -- hash of the whole source file: unchanged files are skipped
  acl          text[] NOT NULL,            -- principals allowed to read: 'public', 'group:support', 'user:c_77'
  updated_at   timestamptz NOT NULL DEFAULT now(),
  deleted_at   timestamptz                 -- tombstone; its chunks are removed
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id    text PRIMARY KEY,            -- doc_id + hash of the chunk text: edits only touch changed chunks
  doc_id      text NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  ord         int NOT NULL,
  context     text NOT NULL,               -- "Title > Section", prepended for search and shown to the model
  content     text NOT NULL,
  embedding   public.vector(384) NOT NULL,
  embed_model text NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', context || ' ' || content)) STORED
);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks (doc_id);
CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_embedding ON chunks USING hnsw (embedding public.vector_cosine_ops);

CREATE TABLE IF NOT EXISTS ingest_jobs (
  id         bigserial PRIMARY KEY,
  doc_path   text NOT NULL,
  op         text NOT NULL CHECK (op IN ('upsert', 'delete')),
  status     text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'dead')),
  attempts   int NOT NULL DEFAULT 0,
  last_error text,
  run_after  timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ingest_jobs_ready ON ingest_jobs (run_after) WHERE status = 'queued';

-- ---- Lab 3: untrusted third-party content ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
  id         serial PRIMARY KEY,
  sku        text NOT NULL,
  rating     int NOT NULL CHECK (rating BETWEEN 1 AND 5),
  body       text NOT NULL,            -- written by strangers: never shown to the tool-using model
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reviews_sku ON reviews (sku);

-- ---- Lab 4: limits, idempotency, background jobs --------------------------------------------------
CREATE TABLE IF NOT EXISTS rate_limits (
  key        text PRIMARY KEY,          -- e.g. 'chat:c_77'
  tokens     double precision NOT NULL, -- token bucket level
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage_daily (
  customer_id text NOT NULL,
  day         date NOT NULL,
  tokens      bigint NOT NULL DEFAULT 0,
  cost_usd    numeric(12, 6) NOT NULL DEFAULT 0,
  PRIMARY KEY (customer_id, day)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  key          text NOT NULL,
  customer_id  text NOT NULL,
  request_hash text NOT NULL,
  status_code  int,                     -- null while the first request is still running
  response     jsonb,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (customer_id, key)
);

CREATE TABLE IF NOT EXISTS jobs (
  id         bigserial PRIMARY KEY,
  kind       text NOT NULL,             -- extract_memory | ...
  dedupe_key text NOT NULL,             -- e.g. the session id: one queued job per session
  payload    jsonb NOT NULL,
  status     text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'dead')),
  attempts   int NOT NULL DEFAULT 0,
  last_error text,
  run_after  timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_one_queued ON jobs (kind, dedupe_key) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS jobs_ready ON jobs (run_after) WHERE status = 'queued';

ALTER TABLE approvals ADD COLUMN IF NOT EXISTS decided_by text;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS tracking_number text;
ALTER TABLE approvals ADD COLUMN IF NOT EXISTS decided_at timestamptz;

-- ---- Lab 5: feedback, online judging, flags ------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedback (
  id          serial PRIMARY KEY,
  session_id  uuid NOT NULL,
  customer_id text NOT NULL,
  rating      text NOT NULL CHECK (rating IN ('up', 'down')),
  reason      text,
  comment     text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS online_judgements (
  id          serial PRIMARY KEY,
  session_id  uuid NOT NULL,
  judge       text NOT NULL,
  verdict     text NOT NULL CHECK (verdict IN ('pass', 'fail')),
  reasoning   text,
  trigger     text NOT NULL,            -- sample | feedback
  reviewed    boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS flags (
  key        text PRIMARY KEY,
  value      jsonb NOT NULL,
  updated_by text,
  updated_at timestamptz NOT NULL DEFAULT now()
);
