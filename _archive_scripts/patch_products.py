import sys

file_path = "app/routers/products.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

injection = """
    if product.product_type == 'parent' and db:
        from app.models.product import Product as ProductModel
        from app.schemas.product_variant import ProductVariantOut
        children = db.query(ProductModel).filter(ProductModel.parent_code == product.id, ProductModel.product_type == 'variant').all()
        v_out = []
        for c in children:
            size = next((a.get('value') for a in (c.attributes or []) if a.get('key') in ('Size', "O'lcham")), None)
            color = next((a.get('value') for a in (c.attributes or []) if a.get('key') in ('Color', 'Rang')), None)
            v_out.append(ProductVariantOut(
                id=c.id,
                product_id=product.id,
                name=c.name,
                sku=c.sku,
                barcode=c.barcode,
                color=color,
                size=size,
                cost_price=c.cost_price,
                sale_price=c.sale_price,
                wholesale_price=c.wholesale_price,
            ))
        out.variants = v_out
"""

search_str = "if product.conversion:"
content = content.replace(search_str, injection + "\n    " + search_str)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("products.py patched!")
