# Usamos la imagen completa de Python para evitar errores de 'apt-get' en redes con firewall
FROM python:3.11

# Evitar que Python genere archivos .pyc y asegurar logs instantáneos
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copiamos requerimientos e instalamos con un tiempo de espera extendido
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

# Copiamos el resto de la lógica (ignora lo definido en .dockerignore)
COPY . .

# Exponemos el puerto 8000 solicitado
EXPOSE 8000

# Comando para iniciar Streamlit
CMD ["streamlit", "run", "app.py", "--server.port", "8000", "--server.address", "0.0.0.0"]