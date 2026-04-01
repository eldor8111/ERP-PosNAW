#!/usr/bin/env python
"""Migrate customer_id column to sales table"""

import psycopg

# Database connection
conn = psycopg.connect(
    "postgresql://postgres:postgres@localhost:5432/erppos"
)

try:
    with conn.cursor() as cur:
        # Check if column exists
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'sales' AND column_name = 'customer_id'
        """)

        if cur.fetchone():
            print("✓ customer_id column already exists in sales table")
        else:
            print("Adding customer_id column to sales table...")

            # Add the column
            cur.execute("ALTER TABLE sales ADD COLUMN customer_id INTEGER")

            # Add foreign key constraint
            cur.execute("""
                ALTER TABLE sales ADD CONSTRAINT fk_sales_customer
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            """)

            conn.commit()
            print("✓ customer_id column added successfully!")

        # Update alembic_version to mark migration as done
        cur.execute("""
            UPDATE alembic_version SET version_num = '94e706f35485'
            WHERE version_num = '93e705f35484'
        """)
        conn.commit()
        print("✓ Alembic version updated")

except Exception as e:
    conn.rollback()
    print(f"✗ Error: {e}")
finally:
    conn.close()

print("\n✓ Migration complete! Please restart your server.")
