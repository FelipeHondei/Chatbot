# Use uma imagem Python oficial
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Copia os arquivos de requisitos
COPY requirements.txt .

# Instala as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Expõe a porta que será usada
EXPOSE 5000

# Comando para executar a aplicação
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "api:app"]