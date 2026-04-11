import os
import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    bot_token: str = Field(default="YOUR_BOT_TOKEN_HERE")
    admin_ids: str = Field(default="") # Через запятую ID админов, например "1234567,9876543"
    admin_it_ids: str = Field(default="") # ID админов для приема IT-заявок
    

    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra='ignore')
    
    @property
    def get_admin_ids(self) -> list[int]:
        if not self.admin_ids:
            return []
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip().isdigit()]

    @property
    def get_admin_it_ids(self) -> list[int]:
        if not self.admin_it_ids:
            return []
        return [int(x.strip()) for x in self.admin_it_ids.split(",") if x.strip().isdigit()]

config = Settings()
