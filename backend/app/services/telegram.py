import os
import time
import logging
from datetime import datetime
from typing import Optional, Tuple
from pathlib import Path
import httpx
from dotenv import load_dotenv

logger = logging.getLogger("telegram_service")

# Load environment variables from .env if present
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class TelegramService:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.enabled = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")
        self.cooldown_seconds = int(os.getenv("TELEGRAM_COOLDOWN_SECONDS", "30"))
        self.last_alert_time = 0.0

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def get_masked_token(self) -> Optional[str]:
        if not self.bot_token:
            return None
        if len(self.bot_token) > 10:
            return self.bot_token[:4] + "..." + self.bot_token[-4:]
        return "****"

    def update_config(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None, enabled: Optional[bool] = None):
        if bot_token is not None and bot_token.strip():
            self.bot_token = bot_token.strip()
        if chat_id is not None and chat_id.strip():
            self.chat_id = chat_id.strip()
        if enabled is not None:
            self.enabled = bool(enabled)

        # Persist to .env file for future restarts
        try:
            lines = []
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").splitlines()

            configs = {
                "TELEGRAM_BOT_TOKEN": self.bot_token,
                "TELEGRAM_CHAT_ID": self.chat_id,
                "TELEGRAM_ENABLED": str(self.enabled).lower(),
                "TELEGRAM_COOLDOWN_SECONDS": str(self.cooldown_seconds)
            }

            new_lines = []
            existing_keys = set()
            for line in lines:
                key = line.split("=")[0].strip() if "=" in line else None
                if key in configs:
                    new_lines.append(f"{key}={configs[key]}")
                    existing_keys.add(key)
                else:
                    new_lines.append(line)

            for key, val in configs.items():
                if key not in existing_keys:
                    new_lines.append(f"{key}={val}")

            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to persist .env file: {e}")

    def send_test_message(self, token: Optional[str] = None, chat: Optional[str] = None) -> Tuple[bool, str]:
        use_token = token.strip() if token else self.bot_token
        use_chat = chat.strip() if chat else self.chat_id

        if not use_token or not use_chat:
            return False, "Bot Token and Chat ID are required."

        url = f"https://api.telegram.org/bot{use_token}/sendMessage"
        payload = {
            "chat_id": use_chat,
            "text": (
                "✅ <b>Face Recognition Camera System</b>\n\n"
                "Telegram Alert is configured successfully!\n"
                "You will receive instant alerts with photos when an unknown person or intruder is detected."
            ),
            "parse_mode": "HTML"
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=payload)
                data = res.json()
                if res.status_code == 200 and data.get("ok"):
                    return True, "Test alert sent successfully to Telegram!"
                else:
                    desc = data.get("description", f"HTTP {res.status_code}")
                    return False, f"Telegram API error: {desc}"
        except Exception as e:
            return False, f"Network error sending to Telegram: {str(e)}"

    def send_intruder_alert(
        self,
        image_bytes: bytes,
        unknown_count: int = 1,
        total_faces: int = 1,
        matched_names: Optional[list] = None
    ) -> bool:
        if not self.enabled or not self.is_configured():
            return False

        current_time = time.time()
        # Rate-limiting cooldown check
        if current_time - self.last_alert_time < self.cooldown_seconds:
            logger.info("Telegram intruder alert suppressed due to cooldown.")
            return False

        self.last_alert_time = current_time
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        matched_str = ""
        if matched_names:
            matched_str = f"\n✅ <b>Recognized present:</b> {', '.join(matched_names)}"

        caption = (
            "🚨 <b>INTRUDER / UNKNOWN PERSON ALERT!</b> 🚨\n"
            "⚠️ An unrecognized person was detected by the Face Recognition Camera.\n\n"
            f"🕒 <b>Time:</b> {timestamp}\n"
            f"👥 <b>Total Faces:</b> {total_faces}\n"
            f"❓ <b>Unknown Faces:</b> {unknown_count}"
            f"{matched_str}\n"
            "📍 <b>Location:</b> Live Camera Monitor"
        )

        photo_url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        try:
            with httpx.Client(timeout=12.0) as client:
                files = {"photo": ("alert.jpg", image_bytes, "image/jpeg")}
                data = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                res = client.post(photo_url, data=data, files=files)
                if res.status_code == 200:
                    logger.info("Telegram photo alert sent successfully.")
                    return True
                else:
                    logger.warning(f"sendPhoto failed: {res.text}. Trying sendMessage fallback.")
        except Exception as e:
            logger.error(f"Error sending Telegram photo alert: {e}")

        # Fallback to plain text message if photo upload fails
        try:
            msg_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            with httpx.Client(timeout=10.0) as client:
                res = client.post(msg_url, json={
                    "chat_id": self.chat_id,
                    "text": caption,
                    "parse_mode": "HTML"
                })
                return res.status_code == 200
        except Exception as e:
            logger.error(f"Error sending Telegram text fallback alert: {e}")
            return False


telegram_service = TelegramService()
