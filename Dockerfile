FROM seleniumbase/seleniumbase:latest

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 5000

ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
