#!/usr/bin/env python
"""Check if customer_id column exists in sales table"""
import sys
sys.path.insert(0, '.')

from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='sales' AND column_name='customer_id'"
    ))
    row = result.fetchone()
    if row:
        print("✓ customer_id column exists in sales table")
    else:
        print("✗ customer_id column DOES NOT exist in sales table")
        print("\nRunning migration to add it...")

        # Add the column
        conn.execute(text("ALTER TABLE sales ADD COLUMN customer_id INTEGER"))
        conn.execute(text(
            "ALTER TABLE sales ADD CONSTRAINT fk_sales_customer "
            "FOREIGN KEY (customer_id) REFERENCES customers(id)"
        ))
        conn.commit()
        print("✓ customer_id column added successfully!")
