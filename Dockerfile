# Imagem ÚNICA para API e UI: os dois processos compartilham o mesmo código e o mesmo
# requirements.txt, então uma imagem só (com comandos diferentes no docker-compose) evita
# build duplo e drift de dependências entre os serviços.
FROM python:3.12-slim

# Logs direto no stdout (docker logs) e sem .pyc dentro do container (imagem mais limpa).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# requirements PRIMEIRO: aproveita o cache de camadas do Docker — mudar código não
# re-instala dependências (rebuild em segundos, não minutos).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código + dados. books.json, o cache de embeddings e os cartões de contexto são COMMITADOS,
# então o container sobe com a recuperação funcionando offline (sem rede na inicialização).
# O .dockerignore garante que .env (segredo), .venv, .git e caches NUNCA entram na imagem.
COPY . .

# Usuário não-root: mesma postura do SECURITY.md (menor privilégio) aplicada ao runtime
# do container — um escape de processo não ganha root no host de container.
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 8501

# Comando default = API; o docker-compose sobrescreve este comando para subir a UI com a
# MESMA imagem. --host 0.0.0.0 é obrigatório: dentro do container, 127.0.0.1 não seria
# alcançável a partir do host.
CMD ["python", "-m", "uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
