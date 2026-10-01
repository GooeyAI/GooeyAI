from celeryapp.celeryconfig import app
from daras_ai_v2.redis_cache import redis_lock
from gooeysite.bg_db_conn import db_middleware
from model_api import billing


@app.task
@db_middleware
def sweep_stale_model_api_calls():
    # beat can overlap a slow run; one sweep at a time
    with redis_lock("gooey/model_api/sweep_stale/v1"):
        return billing.sweep_stale()
