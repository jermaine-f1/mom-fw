from fastapi import FastAPI

from risk_control_ta.api.routes import router
from risk_control_ta.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(router)
