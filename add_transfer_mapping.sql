-- Transfer mahsulot mapping migration
-- Bu skriptni database'da to'g'ridan-to'g'ri ishlatish mumkin

ALTER TABLE stock_transfer_items 
ADD COLUMN IF NOT EXISTS target_product_id INTEGER REFERENCES products(id) ON DELETE SET NULL;

-- Tekshirish
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'stock_transfer_items' 
ORDER BY ordinal_position;
