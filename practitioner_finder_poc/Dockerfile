FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . practitioner_finder_poc/

ENV PORT=8080

EXPOSE 8080

CMD ["streamlit", "run", "practitioner_finder_poc/app.py", \
     "--server.headless", "true", \
     "--server.port", "8080", \
     "--server.address", "0.0.0.0", \
     "--server.enableCORS", "false", \
     "--server.enableXsrfProtection", "false"]
