import sys
sys.path.insert(0, '.')
try:
    from app.main import app  # type: ignore
    routes = [r.path for r in app.routes]
    customer_routes = [r for r in routes if 'customer' in r.lower()]
    print("=== Customer routes ===")
    for r in customer_routes:
        print(r)
    print("\n=== All /api routes ===")
    for r in sorted(routes):
        if '/api' in r:
            print(r)
    print("\nIMPORT OK")
except Exception as e:
    print(f"IMPORT ERROR: {e}")
