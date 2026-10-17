from .audit_log import AuditLog  # type: ignore
from .billing import Tariff  # type: ignore
from .category import Category  # type: ignore
from .company import Company  # type: ignore
from .inventory import StockLevel, StockMovement  # type: ignore
from .product import Product, ProductConversion  # type: ignore
from .sale import Sale, SaleItem, SaleItemBatch  # type: ignore
from .user import User  # type: ignore
from .role import Role  # type: ignore
from .user_company import UserCompany  # type: ignore  # multi-korxona
from .warehouse import Warehouse  # type: ignore
from .supplier import Supplier  # type: ignore
from .purchase_order import PurchaseOrder, POItem, POStatus  # type: ignore
from .batch import Batch  # type: ignore
from .moliya import ExpenseCategory, Expense, Transaction, KassaSession, KassaMovement, PAYMENT_TYPES, CASH_PAYMENT_TYPES, NON_CASH_PAYMENT_TYPES  # type: ignore
from .customer import Customer  # type: ignore
from .shift import Shift  # type: ignore
from .courier import Courier  # type: ignore
from .branch import Branch  # type: ignore
from .currency import Currency, CurrencyRate  # type: ignore
from .api_key import ApiKey  # type: ignore
from .inventory_count import InventoryCount, InventoryCountItem  # type: ignore
from .agent import Agent  # type: ignore
from .transfer import StockTransfer, StockTransferItem, StockTransferBatch  # type: ignore
from .bin_location import BinLocation  # type: ignore
from .label_template import LabelTemplate  # type: ignore  # T3.7
from .payme_transaction import PaymeTransaction  # type: ignore
from .customer_prices import CustomerPrice  # type: ignore
from .mxik import MxikReference, MxikPackage, VatRateType  # type: ignore
from .tovarlar_catalog import TovarlarCatalog  # type: ignore
from .sms_log import SMSLog
from app.admin_tg_bot.models import CompanyBot
from .tg_phone_chat import TgPhoneChat  # type: ignore
from .ai_chat_history import AiChatHistory  # type: ignore
from .bot_session import BotSession  # type: ignore
from .product_variant import ProductVariant
from .promotion import Promotion, PromotionProduct, PromotionBranch  # T4.3: aksiya filiallari
from .branch_price import BranchProductPrice  # type: ignore  # T4.3: filial narxlari
from .supplier_product import SupplierProduct
from .attribute import Attribute, AttributeValue, VariantAttributeValue
from .ai_audit import AIAuditLog
from .announcement import Announcement, SurveyQuestion, SurveyAnswer  # type: ignore
from .bom import BOM, BOMItem  # type: ignore
from .production_order import ProductionOrder, ProductionOrderStatus, ProductionOrderCost  # type: ignore
from .vehicle import Vehicle  # type: ignore
from .customer_document import CustomerDocument  # type: ignore
from .sale_delivery import SaleDelivery, SaleDeliveryStatus  # type: ignore
from .mobile_device import MobileDevice  # type: ignore
from .field_shift import FieldShift  # type: ignore
from .mobile_misc import MobileIdempotency, DeliveryProof  # type: ignore
from .agent_visit import AgentVisit  # type: ignore
from .employee_location import EmployeeLocation  # type: ignore
from .delivery_route import DeliveryRoute, DeliveryRouteStop, DeliveryRouteStatus  # type: ignore
from app.utils.image_pipeline import image_jobs  # noqa: F401  # rasm fonini olib tashlash navbati (Core jadval)
from .marketplace import (  # type: ignore
    MarketplaceAgentCategory, MarketplaceProduct, MarketplaceAgentTransaction,
    MarketplaceProductStatus, MarketplaceTransactionType, MarketplaceAgentNotification,
)
from .order import Order  # type: ignore
from .platform_settings import PlatformSettings  # type: ignore
from .document_counter import DocumentCounter  # type: ignore  # T1.14: hujjat raqamlari hisoblagichi
from .user_branch import UserBranch  # type: ignore  # T1.2: foydalanuvchiga bir nechta filial
from .scheduler_run import SchedulerRun  # type: ignore  # T2.10: scheduler kunlik bajarilish registri
from .background_job import BackgroundLease  # type: ignore  # T3.15: fon jarayon rahbari ijarasi (lease)
from .loyalty import LoyaltySettings, LoyaltyBranchRule  # type: ignore  # T2.12: sodiqlik sozlamalari
from .customer_debt_log import CustomerDebtLog  # type: ignore  # T2.6: mijoz qarzi harakatlari jurnali
from .fiscal_device import FiscalDevice  # type: ignore  # T3.18: fiskal modulning filial/kassaga biriktirilishi
from .payment_terminal import PaymentTerminal  # type: ignore  # T3.18: filial to'lov terminallari
from .warehouse_stock_setting import WarehouseStockSetting  # type: ignore  # T4.4: ombor bo'yicha min/max qoldiq
from .sales_target import SalesTarget  # type: ignore  # T4.7: filial/sotuvchi oylik savdo rejasi
from .employee_commission import EmployeeCommission  # type: ignore  # T4.7: sotuvchi komissiya stavkasi
from .approval import ApprovalRule, ApprovalRequest  # type: ignore  # T4.6: tasdiqlash qoidalari
