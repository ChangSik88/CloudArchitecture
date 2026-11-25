# Docker Hub 요청 한도를 피하려고 ECR Public의 공식 이미지를 쓴다
FROM public.ecr.aws/docker/library/python:3.13-slim

WORKDIR /srv
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
