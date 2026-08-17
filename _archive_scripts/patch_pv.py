import sys

file_path = "app/schemas/product_variant.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "class ProductVariantCreate(ProductVariantBase):",
    "class ProductVariantCreate(ProductVariantBase):\n    id: Optional[int] = None"
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("product_variant.py patched!")
