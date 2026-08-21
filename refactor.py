import os

file_path = "D:\\EcodeWeb\\app\\routers\\auth.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove Telegram bot functions (from _otp_store to _generate_org_code)
import re

content = re.sub(
    r"# Bot orqali ulangan: \{normalized_phone: chat_id\}.*?def _generate_org_code",
    "def _generate_org_code",
    content,
    flags=re.DOTALL
)

# 2. Refactor /send-otp
content = re.sub(
    r"    bot_token = _get_otp_bot_token\(\)\s+is_dev_mode = not bot_token or bot_token == \"YOUR_TELEGRAM_BOT_TOKEN_HERE\"\s+user = db\.query\(User\)",
    "    user = db.query(User)",
    content
)

content = re.sub(
    r"        if is_dev_mode:\s+print\(f\"\[DEV\] Reset OTP for \{normalized\} \(\{user\.name\}\): \{otp\}\"\)\s+else:\s+from app\.services\.eskiz_service import eskiz_service",
    "        from app.services.eskiz_service import eskiz_service",
    content
)

content = re.sub(
    r"        if is_dev_mode:\s+print\(f\"\[DEV\] Register OTP for \{normalized\}: \{otp\}\"\)\s+else:\s+from app\.services\.eskiz_service import eskiz_service",
    "        from app.services.eskiz_service import eskiz_service",
    content
)

content = re.sub(
    r"return \{\"sent\": True, \"dev_mode\": is_dev_mode, \"has_telegram\": True, \"otp_session\": otp_session\}",
    "return {\"sent\": True, \"otp_session\": otp_session}",
    content
)

# 3. Refactor /register (remove _find_chat_id_by_phone)
content = re.sub(
    r"    # Bot orqali ulangan chat_id ni topamiz \(bo'lsa DB ga saqlaymiz\)\s+reg_chat_id = _find_chat_id_by_phone\(data\.phone, db\)",
    "",
    content
)

content = re.sub(
    r"        tg_chat_id=reg_chat_id,",
    "        tg_chat_id=None,",
    content
)

# 4. Refactor /login
content = re.sub(
    r"        bot_token = _get_otp_bot_token\(\)\s+is_dev_mode = not bot_token or bot_token == \"YOUR_TELEGRAM_BOT_TOKEN_HERE\"\s+otp_sent = False\s+if not is_dev_mode:\s+try:",
    "        otp_sent = False\n        try:",
    content
)

content = re.sub(
    r"            except Exception as e:\s+print\(f\"\[OTP Login\] Exception: \{e\}\"\)\s+else:\s+print\(f\"\[OTP Login DEV\] \{normalized_phone\} → \{otp\}\"\)\s+otp_sent = True",
    "        except Exception as e:\n            print(f\"[OTP Login] Exception: {e}\")",
    content
)

content = re.sub(
    r"\"dev_mode\": is_dev_mode,",
    "",
    content
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Refactored auth.py successfully.")
