-- 1. 17185894 tashkiloti bo'yicha jami shtrix kodlar soni va farqli tovar nomlari sonini aniqlash

WITH all_barcodes AS (
    -- 1.1 Asosiy shtrix kodlar
    SELECT barcode, name
    FROM products
    WHERE company_id = 17185894 
      AND is_deleted = false 
      AND barcode IS NOT NULL 
      AND barcode != ''
    
    UNION ALL
    
    -- 1.2 Qo'shimcha shtrix kodlar (extra_barcodes JSON fielddan o'qib olish)
    SELECT json_array_elements_text(extra_barcodes::json) AS barcode, name
    FROM products
    WHERE company_id = 17185894 
      AND is_deleted = false 
      AND extra_barcodes IS NOT NULL 
      AND extra_barcodes != '' 
      AND extra_barcodes != '[]'
)
SELECT 
    COUNT(barcode) AS "Shtrix kodlar jami soni (har bir shtrix bitta tovar)",
    COUNT(DISTINCT name) AS "Farqli tovar nomlari soni"
FROM all_barcodes;

---------------------------------------------------------------------------

-- 2. Bitta nomga bir nechta shtrix kod biriktirilgan tovarlarni va ularning shtrix kodlarini ro'yxatini chiqarish

WITH all_barcodes AS (
    SELECT name, barcode
    FROM products
    WHERE company_id = 17185894 AND is_deleted = false AND barcode IS NOT NULL AND barcode != ''
    
    UNION ALL
    
    SELECT name, json_array_elements_text(extra_barcodes::json) AS barcode
    FROM products
    WHERE company_id = 17185894 AND is_deleted = false AND extra_barcodes IS NOT NULL AND extra_barcodes != '' AND extra_barcodes != '[]'
)
SELECT 
    name AS "Tovar nomi", 
    COUNT(barcode) AS "Biriktirilgan shtrix kodlar soni", 
    string_agg(barcode, ', ') AS "Shtrix kodlar"
FROM all_barcodes
GROUP BY name
HAVING COUNT(barcode) > 1
ORDER BY COUNT(barcode) DESC;
