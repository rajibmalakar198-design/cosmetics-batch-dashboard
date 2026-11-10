# Cosmetics Brand & Product Batch Dashboard

A relational database app (SQLite + Tkinter) that replaces a spreadsheet-based
formulation tracking system.

## Features
- 3 tables (brands, product_batches, ingredient_items) with foreign keys
- ON DELETE CASCADE at both relationship levels
- Auto-seeded sample data when the database is empty
- Insert panel: reuses an existing brand or creates a new one
- Delete panel with dynamic dropdowns (brand / batch / ingredient)
- 4 live tabs: joined view + 3 raw tables
- Input validation (blank, non-numeric, zero, negative)

## Requirements
Python 3.8+. No third-party packages (sqlite3 and tkinter are built in).

## How to run
    python cosmetics_app.py

The database file `cosmetics.db` is created automatically on first run.

## ER Diagram
brands (1) ──< product_batches (many) ──< ingredient_items (many)

## Author
Rajib Malakar 
