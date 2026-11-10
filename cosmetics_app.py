import sqlite3
import os
import re
from datetime import date
import tkinter as tk
from tkinter import ttk, messagebox

# Database file is created next to this script
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cosmetics.db")


# ---------- DATABASE LAYER ----------

def get_connection():
    """Open a connection. PRAGMA must run on EVERY connection,
    otherwise SQLite silently ignores foreign keys and cascades."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables(conn):
    conn.executescript("""
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
            FOREIGN KEY (brand_id) REFERENCES brands(brand_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ingredient_items (
            item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id        INTEGER NOT NULL,
            ingredient_name TEXT NOT NULL,
            quantity_g      REAL NOT NULL CHECK (quantity_g > 0),
            FOREIGN KEY (batch_id) REFERENCES product_batches(batch_id)
                ON DELETE CASCADE
        );
    """)
    conn.commit()


def make_placeholder_email(brand_name):
    """Option A: auto-generate an email for brands created from the GUI.
    'Glow Lab' -> 'noreply@glowlab.com'"""
    slug = re.sub(r"[^a-z0-9]", "", brand_name.lower()) or "brand"
    return f"noreply@{slug}.com"


def seed_if_empty(conn):
    """Insert sample data ONLY if the database has no brands."""
    count = conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0]
    if count > 0:
        return False  # already has data, do nothing

    brands = [
        ("Velvet Bloom", "manager@velvetbloom.com"),
        ("Glow Lab", "contact@glowlab.com"),
        ("Terra Naturals", "ops@terranaturals.com"),
    ]
    conn.executemany(
        "INSERT INTO brands (brand_name, manager_email) VALUES (?, ?)", brands
    )

    # (brand_id, product_name, manufacture_date)
    batches = [
        (1, "Matte Lipstick - Ruby Red", "2026-09-01"),
        (1, "Hydrating Day Cream",       "2026-09-12"),
        (2, "Vitamin C Serum",           "2026-09-20"),
        (3, "Shea Body Butter",          "2026-10-02"),
    ]
    conn.executemany(
        "INSERT INTO product_batches (brand_id, product_name, manufacture_date) "
        "VALUES (?, ?, ?)", batches
    )

    # (batch_id, ingredient_name, quantity_g)
    items = [
        (1, "Titanium Dioxide", 120.0),
        (1, "Castor Oil",       300.0),
        (2, "Shea Butter",      450.5),
        (2, "Fragrance Oil",     15.0),
        (3, "Ascorbic Acid",     80.0),
        (3, "Glycerin",         250.0),
        (4, "Shea Butter",      900.0),
        (4, "Fragrance Oil",     20.0),
    ]
    conn.executemany(
        "INSERT INTO ingredient_items (batch_id, ingredient_name, quantity_g) "
        "VALUES (?, ?, ?)", items
    )
    conn.commit()
    return True


# ---------- QUERY HELPERS ----------

# Whitelist: table names can't be passed as ? placeholders,
# so we only allow known names (prevents SQL injection).
RAW_TABLES = {
    "brands": "SELECT brand_id, brand_name, manager_email FROM brands ORDER BY brand_id",
    "product_batches": "SELECT batch_id, brand_id, product_name, manufacture_date "
                       "FROM product_batches ORDER BY batch_id",
    "ingredient_items": "SELECT item_id, batch_id, ingredient_name, quantity_g "
                        "FROM ingredient_items ORDER BY item_id",
}


def _run_query(conn, sql, params=()):
    """Run a SELECT and return (column_names, rows)."""
    cur = conn.execute(sql, params)
    columns = [d[0] for d in cur.description]
    return columns, cur.fetchall()


def fetch_join(conn):
    """Tab 1: brands + batches + ingredients in one view.
    INNER JOIN is safe: NOT NULL foreign keys mean no orphans exist."""
    sql = """
        SELECT pb.batch_id         AS "Batch ID",
               b.brand_name        AS "Brand Name",
               pb.product_name     AS "Product Name",
               pb.manufacture_date AS "Manufacture Date",
               ii.ingredient_name  AS "Ingredient Name",
               ii.quantity_g       AS "Quantity (g)"
        FROM product_batches pb
        JOIN brands b            ON b.brand_id = pb.brand_id
        JOIN ingredient_items ii ON ii.batch_id = pb.batch_id
        ORDER BY pb.batch_id, ii.item_id
    """
    return _run_query(conn, sql)


def fetch_table(conn, table_name):
    """Tabs 2-4: raw view of one table. Only whitelisted names allowed."""
    if table_name not in RAW_TABLES:
        raise ValueError(f"Unknown table: {table_name}")
    return _run_query(conn, RAW_TABLES[table_name])


def fetch_dropdown_options(conn, kind):
    """Delete-panel dropdown. Returns a list of (id, label) tuples.
    kind is 'Brand', 'Batch' or 'Ingredient'."""
    if kind == "Brand":
        sql = "SELECT brand_id, brand_name FROM brands ORDER BY brand_id"
        return [(i, f"{i} - {name}") for i, name in conn.execute(sql)]
    if kind == "Batch":
        sql = "SELECT batch_id, product_name FROM product_batches ORDER BY batch_id"
        return [(i, f"{i} - {name}") for i, name in conn.execute(sql)]
    if kind == "Ingredient":
        sql = ("SELECT item_id, ingredient_name, batch_id "
               "FROM ingredient_items ORDER BY item_id")
        return [(i, f"{i} - {name} (Batch {b})")
                for i, name, b in conn.execute(sql)]
    raise ValueError(f"Unknown kind: {kind}")


# ---------- LOGIC LAYER: VALIDATION + INSERT ----------

def validate_inputs(brand, product, ingredient, qty_text):
    """Returns (ok, message_or_cleaned_values).
    On failure: (False, "error text").
    On success: (True, (brand, product, ingredient, qty_float))."""
    brand = brand.strip()
    product = product.strip()
    ingredient = ingredient.strip()
    qty_text = qty_text.strip()

    if not brand or not product or not ingredient or not qty_text:
        return False, "All fields are required. Please fill in every box."

    try:
        qty = float(qty_text)
    except ValueError:
        return False, "Quantity must be a number (e.g. 25 or 12.5)."

    # float("nan") and float("inf") parse successfully, so block them explicitly
    if qty != qty or qty in (float("inf"), float("-inf")):
        return False, "Quantity must be a real number."

    if qty <= 0:
        return False, "Quantity must be greater than zero."

    return True, (brand, product, ingredient, qty)


def get_or_create_brand(conn, brand_name):
    """If the brand exists, return its ID. Otherwise create it (Option A email)."""
    row = conn.execute(
        "SELECT brand_id FROM brands WHERE brand_name = ? COLLATE NOCASE",
        (brand_name,),
    ).fetchone()
    if row:
        return row[0]

    cur = conn.execute(
        "INSERT INTO brands (brand_name, manager_email) VALUES (?, ?)",
        (brand_name, make_placeholder_email(brand_name)),
    )
    return cur.lastrowid


def add_record(conn, brand, product, ingredient, qty_text):
    """Validate, then insert 1 batch + 1 ingredient under the brand.
    Returns (success, message)."""
    ok, result = validate_inputs(brand, product, ingredient, qty_text)
    if not ok:
        return False, result

    brand, product, ingredient, qty = result
    try:
        brand_id = get_or_create_brand(conn, brand)

        cur = conn.execute(
            "INSERT INTO product_batches (brand_id, product_name, manufacture_date) "
            "VALUES (?, ?, ?)",
            (brand_id, product, date.today().isoformat()),
        )
        batch_id = cur.lastrowid

        conn.execute(
            "INSERT INTO ingredient_items (batch_id, ingredient_name, quantity_g) "
            "VALUES (?, ?, ?)",
            (batch_id, ingredient, qty),
        )
        conn.commit()
        return True, f"Added batch {batch_id} under brand ID {brand_id}."
    except sqlite3.Error as e:
        conn.rollback()  # undo partial inserts
        return False, f"Database error: {e}"

# ---------- LOGIC LAYER: DELETE ----------

# Whitelist: table and column names can't be ? placeholders
DELETE_MAP = {
    "Brand":      ("brands",           "brand_id"),
    "Batch":      ("product_batches",  "batch_id"),
    "Ingredient": ("ingredient_items", "item_id"),
}


def count_children(conn, kind, record_id):
    """Returns (batches, ingredients) that a delete would remove as a side effect.
    Used by the GUI to warn the user before a cascading delete."""
    if kind == "Brand":
        batches = conn.execute(
            "SELECT COUNT(*) FROM product_batches WHERE brand_id = ?", (record_id,)
        ).fetchone()[0]
        items = conn.execute(
            "SELECT COUNT(*) FROM ingredient_items WHERE batch_id IN "
            "(SELECT batch_id FROM product_batches WHERE brand_id = ?)", (record_id,)
        ).fetchone()[0]
        return batches, items
    if kind == "Batch":
        items = conn.execute(
            "SELECT COUNT(*) FROM ingredient_items WHERE batch_id = ?", (record_id,)
        ).fetchone()[0]
        return 0, items
    return 0, 0  # deleting an Ingredient removes nothing else


def delete_record(conn, kind, record_id):
    """Delete ONE row from ONE table. Cascades handle the children.
    Returns (success, message)."""
    if kind not in DELETE_MAP:
        return False, "Please choose what to delete."
    if record_id is None:
        return False, "Please select an item to delete."

    table, id_col = DELETE_MAP[kind]
    try:
        cur = conn.execute(f"DELETE FROM {table} WHERE {id_col} = ?", (record_id,))
        conn.commit()
        if cur.rowcount == 0:
            return False, f"{kind} {record_id} no longer exists."
        return True, f"Deleted {kind} {record_id}."
    except sqlite3.Error as e:
        conn.rollback()
        return False, f"Database error: {e}"
    
# ---------- GUI LAYER ----------

TAB_TITLES = ["Joined View", "Brands", "Product Batches", "Ingredient Items"]


class CosmeticsApp:
    def __init__(self, root, conn):
        self.root = root
        self.conn = conn
        root.title("Cosmetics Brand & Batch Dashboard")
        root.geometry("1000x650")

        # Tk variables hold what the user types or selects
        self.brand_var = tk.StringVar()
        self.product_var = tk.StringVar()
        self.ingredient_var = tk.StringVar()
        self.qty_var = tk.StringVar()
        self.kind_var = tk.StringVar(value="Brand")
        self.target_var = tk.StringVar()

        self._build_insert_panel()
        self._build_delete_panel()
        self._build_tabs()
        self.kind_combo.bind("<<ComboboxSelected>>", self.on_kind_change)
        self.option_ids = []      # IDs matching the dropdown rows
        self.refresh_all()

    # ----- Insert panel -----
    def _build_insert_panel(self):
        frame = ttk.LabelFrame(self.root, text="Insert Panel", padding=10)
        frame.pack(fill="x", padx=10, pady=(10, 5))

        fields = [
            ("Brand Name", self.brand_var),
            ("Product Name", self.product_var),
            ("Ingredient", self.ingredient_var),
            ("Quantity (g)", self.qty_var),
        ]
        for col, (label, var) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=0, column=col, sticky="w", padx=5)
            ttk.Entry(frame, textvariable=var, width=22).grid(
                row=1, column=col, padx=5, pady=(0, 5)
            )

        ttk.Button(frame, text="Add Record", command=self.on_add).grid(
            row=1, column=4, padx=10
        )

    # ----- Delete panel -----
    def _build_delete_panel(self):
        frame = ttk.LabelFrame(self.root, text="Delete Panel", padding=10)
        frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame, text="Delete by").grid(row=0, column=0, sticky="w", padx=5)
        self.kind_combo = ttk.Combobox(
            frame, textvariable=self.kind_var, state="readonly", width=15,
            values=["Brand", "Batch", "Ingredient"],
        )
        self.kind_combo.grid(row=1, column=0, padx=5)

        ttk.Label(frame, text="Select item").grid(row=0, column=1, sticky="w", padx=5)
        self.target_combo = ttk.Combobox(
            frame, textvariable=self.target_var, state="readonly", width=45
        )
        self.target_combo.grid(row=1, column=1, padx=5)

        ttk.Button(frame, text="Delete Selected", command=self.on_delete).grid(
            row=1, column=2, padx=10
        )

    # ----- Tabbed display -----
    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.trees = {}  # tab title -> Treeview
        for title in TAB_TITLES:
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text=title)

            tree = ttk.Treeview(tab, show="headings")
            ysb = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=ysb.set)
            tree.pack(side="left", fill="both", expand=True)
            ysb.pack(side="right", fill="y")
            self.trees[title] = tree

        # ----- Refresh logic -----
    def _fill_tree(self, tree, columns, rows):
        """Clear old rows first, otherwise every refresh duplicates the data."""
        tree.delete(*tree.get_children())
        tree["columns"] = columns
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=140, anchor="w")
        for row in rows:
            tree.insert("", "end", values=row)

    def refresh_tables(self):
        cols, rows = fetch_join(self.conn)
        self._fill_tree(self.trees["Joined View"], cols, rows)

        for title, table in (("Brands", "brands"),
                             ("Product Batches", "product_batches"),
                             ("Ingredient Items", "ingredient_items")):
            cols, rows = fetch_table(self.conn, table)
            self._fill_tree(self.trees[title], cols, rows)

    def refresh_dropdown(self):
        """Rebuild options from the DB and reset the selection,
        so it can never point at a deleted ID."""
        options = fetch_dropdown_options(self.conn, self.kind_var.get())
        self.option_ids = [opt_id for opt_id, _ in options]
        self.target_combo["values"] = [label for _, label in options]
        if options:
            self.target_combo.current(0)
        else:
            self.target_var.set("")

    def refresh_all(self):
        self.refresh_tables()
        self.refresh_dropdown()

    def on_kind_change(self, event=None):
        self.refresh_dropdown()

    # ----- Button handlers -----
    def on_add(self):
        ok, msg = add_record(
            self.conn,
            self.brand_var.get(), self.product_var.get(),
            self.ingredient_var.get(), self.qty_var.get(),
        )
        if not ok:
            messagebox.showerror("Invalid input", msg)
            return  # keep what the user typed so they can fix it

        for var in (self.brand_var, self.product_var,
                    self.ingredient_var, self.qty_var):
            var.set("")
        self.refresh_all()
        messagebox.showinfo("Success", msg)

    def on_delete(self):
        index = self.target_combo.current()
        if index < 0 or index >= len(self.option_ids):
            messagebox.showwarning("Nothing selected", "Please select an item to delete.")
            return

        kind = self.kind_var.get()
        record_id = self.option_ids[index]

        batches, items = count_children(self.conn, kind, record_id)
        warning = f"Delete {kind} {record_id}?"
        if kind == "Brand":
            warning += f"\n\nThis also deletes {batches} batch(es) and {items} ingredient item(s)."
        elif kind == "Batch":
            warning += f"\n\nThis also deletes {items} ingredient item(s)."
        if not messagebox.askyesno("Confirm delete", warning):
            return

        ok, msg = delete_record(self.conn, kind, record_id)
        self.refresh_all()   # runs even on failure, to fix stale lists
        if ok:
            messagebox.showinfo("Deleted", msg)
        else:
            messagebox.showwarning("Not deleted", msg)

# ---------- MAIN ----------
if __name__ == "__main__":
    conn = get_connection()
    create_tables(conn)
    seed_if_empty(conn)

    root = tk.Tk()
    CosmeticsApp(root, conn)
    root.mainloop()
    conn.close()