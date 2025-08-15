from flask import Flask, request, jsonify
import os
import sqlite3
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime
from flask_cors import CORS
import threading

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)
CORS(app)  # Habilita CORS para permitir requisições do frontend

# Lock para operações thread-safe no banco de dados
db_lock = threading.Lock()

# Classe de Gerenciamento de Banco de Dados
class ChatbotDatabase:
    def __init__(self, db_path='chatbot.db'):
        """
        Inicializa o banco de dados SQLite
        Cria tabelas se não existirem
        """
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Inicializa o banco de dados com as tabelas necessárias"""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Criar tabela de conversas
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_message TEXT,
                ai_response TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Criar tabela de conhecimento
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                key TEXT,
                value TEXT,
                UNIQUE(category, key)
            )
            ''')
            
            conn.commit()
            conn.close()
    
    def _get_connection(self):
        """Obtém uma nova conexão com o banco de dados"""
        return sqlite3.connect(self.db_path, timeout=20.0)
    
    def save_conversation(self, user_message, ai_response):
        """
        Salva uma entrada de conversa no banco de dados
        """
        try:
            with db_lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO conversations (user_message, ai_response) 
                VALUES (?, ?)
                ''', (user_message, ai_response))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            print(f"Erro ao salvar conversa: {e}")
            return False
    
    def save_knowledge(self, category, key, value):
        """
        Salva um par de conhecimento no banco de dados
        Substitui se já existir
        """
        try:
            with db_lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO knowledge (category, key, value) 
                VALUES (?, ?, ?)
                ''', (category, key, value))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            print(f"Erro ao salvar conhecimento: {e}")
            return False
    
    def get_knowledge(self, category, key):
        """
        Recupera um valor de conhecimento específico
        """
        try:
            with db_lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                SELECT value FROM knowledge 
                WHERE category = ? AND key = ?
                ''', (category, key))
                result = cursor.fetchone()
                conn.close()
                return result[0] if result else None
        except Exception as e:
            print(f"Erro ao recuperar conhecimento: {e}")
            return None
    
    def get_conversation_history(self, limit=10):
        """
        Recupera o histórico de conversas
        """
        try:
            with db_lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                SELECT user_message, ai_response 
                FROM conversations 
                ORDER BY timestamp DESC 
                LIMIT ?
                ''', (limit,))
                result = cursor.fetchall()
                conn.close()
                return result
        except Exception as e:
            print(f"Erro ao recuperar histórico: {e}")
            return []

# Classe do Chatbot
class Chatbot:
    def __init__(self, api_key):
        """
        Inicializa o chatbot com banco de dados e cliente de IA
        """
        # Inicializa banco de dados
        self.db = ChatbotDatabase()
        
        # Inicializa cliente Groq
        self.client = Groq(api_key=api_key)
    
    def generate_response(self, prompt, context=None):
        """
        Gera resposta usando o modelo de IA
        Pode incluir contexto adicional
        """
        # Prepara mensagens
        messages = [
            {
                "role": "system",
                "content": "Você é um assistente de IA. Seu nome é Laponia. Responda às perguntas do usuário da melhor forma possível."
            }
        ]
        
        # Adiciona contexto se existir
        if context:
            messages.append({
                "role": "system",
                "content": f"Contexto adicional: {context}"
            })
        
        # Adiciona mensagem do usuário
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        # Gera resposta
        chat_completion = self.client.chat.completions.create(
            messages=messages,
            model="llama3-8b-8192"
        )
        
        return chat_completion.choices[0].message.content
    
    def process_message(self, user_message):
        """
        Processa uma mensagem do usuário e retorna uma resposta
        """
        try:
            # Recupera contexto (últimas entradas)
            historico_conversa = self.db.get_conversation_history(2)
            contexto = " ".join([f"{msg[0]} -> {msg[1]}" for msg in historico_conversa])
            
            # Gera resposta
            resposta = self.generate_response(user_message, contexto)
            
            # Salva conversa no banco de dados
            self.db.save_conversation(user_message, resposta)
            
            return resposta
        except Exception as e:
            print(f"Erro no processamento da mensagem: {e}")
            return f"Desculpe, ocorreu um erro: {str(e)}"

# Cria instância do chatbot
try:
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise ValueError("Nenhuma chave de API da Groq encontrada. Verifique as variáveis de ambiente")
    
    chatbot = Chatbot(groq_api_key)
    print("Chatbot inicializado com sucesso!")
except Exception as e:
    print(f"Erro ao inicializar o chatbot: {e}")
    chatbot = None

# Rotas da API
@app.route('/', methods=['GET'])
def home():
    """
    Rota principal para verificar se a API está funcionando
    """
    return jsonify({
        "message": "API Chatbot Laponia está funcionando!",
        "status": "healthy",
        "chatbot_initialized": chatbot is not None
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Endpoint para processar mensagens do usuário
    """
    if not chatbot:
        return jsonify({"error": "Chatbot não inicializado corretamente"}), 500
    
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"error": "Formato de requisição inválido. Envie um JSON com o campo 'message'"}), 400
    
    user_message = data['message']
    
    # Verifica se é um comando especial
    if user_message.startswith('/salvar'):
        # Exemplo: /salvar categoria:chave:valor
        parts = user_message.split(':')
        if len(parts) >= 3:
            categoria = parts[0].replace('/salvar', '').strip()
            chave = parts[1].strip()
            valor = ':'.join(parts[2:]).strip()
            
            success = chatbot.db.save_knowledge(categoria, chave, valor)
            if success:
                return jsonify({"response": f"Conhecimento salvo: {categoria}:{chave}"})
            else:
                return jsonify({"response": "Erro ao salvar conhecimento"})
    
    if user_message.startswith('/recuperar'):
        # Exemplo: /recuperar categoria:chave
        parts = user_message.split(':')
        if len(parts) == 2:
            categoria = parts[0].replace('/recuperar', '').strip()
            chave = parts[1].strip()
            
            valor = chatbot.db.get_knowledge(categoria, chave)
            if valor:
                return jsonify({"response": f"Valor recuperado: {valor}"})
            else:
                return jsonify({"response": "Conhecimento não encontrado"})
    
    # Processa mensagem normal
    response = chatbot.process_message(user_message)
    return jsonify({"response": response})

@app.route('/api/history', methods=['GET'])
def get_history():
    """
    Endpoint para recuperar histórico de conversas
    """
    if not chatbot:
        return jsonify({"error": "Chatbot não inicializado corretamente"}), 500
    
    limit = request.args.get('limit', default=10, type=int)
    history = chatbot.db.get_conversation_history(limit)
    
    # Converte para formato de lista de dicionários
    formatted_history = [
        {"user_message": msg[0], "ai_response": msg[1]} 
        for msg in history
    ]
    
    return jsonify({"history": formatted_history})

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Endpoint para verificar se a API está funcionando
    """
    return jsonify({
        "status": "healthy", 
        "chatbot_initialized": chatbot is not None,
        "timestamp": datetime.now().isoformat()
    })

@app.errorhandler(Exception)
def handle_error(e):
    """
    Manipulador global de erros
    """
    print(f"Erro na API: {str(e)}")
    return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)