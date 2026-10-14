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
