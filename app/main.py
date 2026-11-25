"""2주차 테스트 API.

같은 이미지를 식품관(food)과 패션관(fashion) ECS 서비스에 배포하고,
환경 변수 SERVICE_NAME으로 어느 서비스인지 구분한다.
"""

import json
import os
import time
import urllib.request
import uuid

import boto3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

SERVICE = os.environ.get("SERVICE_NAME", "local")
TABLE = os.environ.get("TABLE_NAME")
LOG_TTL_DAYS = 30

app = FastAPI(title=f"ragbot-{SERVICE}")
_table = None


def _own(service: str) -> None:
    # 다른 서비스 경로로 들어온 요청은 받지 않는다 (ALB 규칙이 잘못돼도 섞이지 않게)
    if service != SERVICE:
        raise HTTPException(404, f"this task serves '{SERVICE}' only")


def _task_metadata() -> dict:
    # Fargate가 넣어 주는 작업 메타데이터 엔드포인트 (로컬 실행 시에는 없음)
    uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
    if not uri:
        return {"availabilityZone": "local", "taskId": "local"}
    with urllib.request.urlopen(f"{uri}/task", timeout=2) as r:
        meta = json.loads(r.read())
    return {
        "availabilityZone": meta.get("AvailabilityZone"),
        "taskId": meta.get("TaskARN", "").rsplit("/", 1)[-1],
    }


def _chat_table():
    global _table
    if _table is None:
        if not TABLE:
            raise HTTPException(503, "TABLE_NAME is not set")
        _table = boto3.resource("dynamodb").Table(TABLE)
    return _table


class LogIn(BaseModel):
    message: str


@app.get("/api/{service}/health")
def health(service: str):
    _own(service)
    return {"service": SERVICE, "status": "ok"}


@app.get("/api/{service}/info")
def info(service: str):
    _own(service)
    return {"service": SERVICE, **_task_metadata()}


@app.post("/api/{service}/log")
def write_log(service: str, body: LogIn):
    """대화 기록 쓰기 테스트. 작업 역할에는 PutItem만 있고 읽기 권한은 없다."""
    _own(service)
    now = int(time.time())
    item = {
        "id": str(uuid.uuid4()),
        "createdAt": now,
        "message": body.message,
        "expiresAt": now + LOG_TTL_DAYS * 86400,
    }
    _chat_table().put_item(Item=item)
    return {"service": SERVICE, "saved": item["id"], "table": TABLE}
