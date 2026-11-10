PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS brands (
    brand_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_name    TEXT NOT NULL UNIQUE,
    manager_email TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_batches (
    batch_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id         INTEGER NOT NULL,
    product_name     TEXT NOT NULL,
    manufacture_date TEXT NOT NULL,
    FOREIGN KEY (brand_id) REFERENCES brands(brand_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ingredient_items (
    item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        INTEGER NOT NULL,
    ingredient_name TEXT NOT NULL,
    quantity_g      REAL NOT NULL CHECK (quantity_g > 0),
    FOREIGN KEY (batch_id) REFERENCES product_batches(batch_id) ON DELETE CASCADE
);