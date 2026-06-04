FROM python:3.12-alpine
RUN pip install --no-cache-dir flask requests
COPY relay.py /app/relay.py
CMD ["python", "/app/relay.py"]
