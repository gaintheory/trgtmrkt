-- De-identified deals: one row per sale. No names, phones, street addresses,
-- license numbers, employers, birthdays, credit scores or incomes.
-- deal_id is a salted hash of the lot + Frazer stock number.
CREATE TABLE IF NOT EXISTS deals (
  deal_id          TEXT PRIMARY KEY,
  lot              TEXT NOT NULL,
  sale_date        TEXT,
  year             INTEGER,
  make             TEXT,
  model            TEXT,
  mileage_at_sale  INTEGER,
  sale_price       REAL,
  down_payment     REAL,
  amount_financed  REAL,
  apr              REAL,
  term_payments    INTEGER,
  payment_amount   REAL,
  payment_frequency TEXT,
  total_cost       REAL,
  profit_on_sale   REAL,
  days_on_lot      INTEGER,
  -- active | paid_off | repossessed | charged_off | cash | wholesale | outside_financing | unknown
  status           TEXT NOT NULL DEFAULT 'unknown',
  days_past_due    INTEGER,
  repo_date        TEXT,
  zip5             TEXT,
  sale_type        TEXT,   -- BHPH / Cash / Wholesale / Outside Financing (as Frazer spells it)
  vehicle_source   TEXT,   -- Auction / Repossession / Trade / Company ...
  purchase_date    TEXT,
  original_cost    REAL,
  added_costs      REAL
);
CREATE INDEX IF NOT EXISTS deals_lot_idx ON deals(lot);

-- One row per listing sighting per weekly pull (competitor pricing, DOM).
CREATE TABLE IF NOT EXISTS listing_snapshots (
  snapshot_date TEXT NOT NULL,
  vin           TEXT NOT NULL,
  year          INTEGER,
  make          TEXT,
  model         TEXT,
  price         REAL,
  mileage       REAL,
  dealer        TEXT,
  zip           TEXT,
  raw           TEXT,
  PRIMARY KEY (snapshot_date, vin)
);

-- Every paid API call, so quotas are enforced rather than hoped for.
CREATE TABLE IF NOT EXISTS api_calls (
  called_at TEXT NOT NULL,
  provider  TEXT NOT NULL,
  endpoint  TEXT NOT NULL,
  params    TEXT,
  status    INTEGER
);

-- Free public data. ACS lives in acs_zcta (replaced wholesale on refresh).
CREATE TABLE IF NOT EXISTS county_unemployment (
  fips TEXT NOT NULL, month TEXT NOT NULL, rate REAL,
  PRIMARY KEY (fips, month)
);
CREATE TABLE IF NOT EXISTS macro_series (
  series TEXT NOT NULL, date TEXT NOT NULL, value REAL,
  PRIMARY KEY (series, date)
);
-- FRED series metadata. copyrighted=1 means the notes contain "Copyright": the
-- series belongs to a third party and is not stored without their permission.
CREATE TABLE IF NOT EXISTS macro_series_meta (
  series TEXT PRIMARY KEY, title TEXT, copyrighted INTEGER NOT NULL DEFAULT 0, checked_at TEXT
);
CREATE TABLE IF NOT EXISTS vin_decode (
  vin TEXT PRIMARY KEY, body_class TEXT, drive_type TEXT, fuel TEXT,
  displacement_l TEXT, cylinders TEXT, error_code TEXT
);

-- Current unsold stock (Frazer inventory export). Vendor is a business name.
CREATE TABLE IF NOT EXISTS inventory (
  unit_id        TEXT PRIMARY KEY,
  lot            TEXT NOT NULL,
  year           INTEGER, make TEXT, model TEXT, mileage INTEGER,
  original_cost  REAL, added_costs REAL, retail_price REAL,
  purchase_date  TEXT, ready_date TEXT,
  vendor         TEXT,
  snapshot_date  TEXT
);
