-- purchase_orders jadvaliga to'langan summa va chegirma maydonlarini qo'shish
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(14,2) DEFAULT 0;
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(14,2) DEFAULT 0;
