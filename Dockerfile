# Multi-stage build for Sapakata Creative Hub
FROM python:3.11-slim as builder

WORKDIR /tmp
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app_improved.py .
COPY requirements.txt .

ENV PATH="/opt/venv/bin:$PATH"
ENV FLASK_APP=app_improved.py
ENV PYTHONUNBUFFERED=1

RUN useradd -m -u 1000 sapakata && chown -R sapakata:sapakata /app
USER sapakata

EXPOSE 5000

# Use gunicorn with explicit app reference
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app_improved:app"]
