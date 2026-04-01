#!/usr/bin/env python3
import subprocess
import sys

# Try to import psycopg2 or psycopg
try:
    import psycopg2 as psycopg
    use_psycopg2 = True
except ImportError:
    try:
        import psycopg
        use_psycopg2 = False
    except ImportError:
        print("Installing psycopg...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
        import psycopg2 as psycopg
        use_psycopg2 = True

# Database connection
try:
    conn = psycopg.connect(
        host="localhost",
        port=5432,
        database="erppos",
        user="postgres",
        password="postgres"
    )
    conn.autocommit = True

    print("✓ Connected to database")

    with conn.cursor() as cur:
        # Check if column exists
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'sales' AND column_name = 'customer_id'
        """)

        if cur.fetchone():
            print("✓ customer_id column already exists")
        else:
            print("→ Adding customer_id column...")

            # Add the column
            cur.execute("ALTER TABLE sales ADD COLUMN customer_id INTEGER")
            print("  ✓ Column added")

            # Add foreign key constraint
            try:
                cur.execute("""
                    ALTER TABLE sales ADD CONSTRAINT fk_sales_customer
                    FOREIGN KEY (customer_id) REFERENCES customers(id)
                """)
                print("  ✓ Foreign key constraint added")
            except Exception as e:
                if "already exists" in str(e):
                    print("  ✓ Foreign key already exists")
                else:
                    raise

        # Update alembic version
        cur.execute("SELECT version_num FROM alembic_version")
        current_version = cur.fetchone()[0]
        print(f"→ Current alembic version: {current_version}")

        if current_version == '93e705f35484':
            cur.execute("UPDATE alembic_version SET version_num = '94e706f35485'")
            print("  ✓ Alembic version updated to 94e706f35485")
        elif current_version == '94e706f35485':
            print("  ✓ Already at correct version")
        else:
            print(f"  ! Version is {current_version}, manual check needed")

        print("\n✅ Migration complete!")
        print("Please restart your FastAPI server now.")

except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
finally:
    if 'conn' in locals():
        conn.close()
