# 后端镜像：生产启动用 gunicorn 托管 uvicorn workers
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY server/requirements.txt ./requirements.txt
# 复刻本机已验证的混装组合（checkpoint 4.3.0 + sqlite-saver 3.1.2 与 langgraph 0.2.53
# 在 pip 元数据上冲突，但运行时兼容）——--no-deps 覆盖安装绕过 resolver
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt && \
    pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple --no-deps \
        langgraph-checkpoint==4.3.0 langgraph-checkpoint-sqlite==3.1.2

COPY server/app ./app
COPY server/sensitive_words.txt ./sensitive_words.txt

EXPOSE 8000

# 生产级启动：4 个 uvicorn worker（按需调整）
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000", "app.main:app"]
