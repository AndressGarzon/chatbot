from flask import Flask, render_template, request, jsonify, session
from openai import OpenAI
from dotenv import load_dotenv
import os
import time
import json
import logging
from datetime import datetime
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables del archivo .env
load_dotenv()

app.secret_key = os.getenv("SECRET_KEY", "clave_secreta_desarrollo_2024")

# Configuración para sesiones
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutos

# Crear cliente con la API key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class VeterinarioChatbotAvanzado:
    def __init__(self):
        self.temas_mascotas = {
            "perros": ["perro", "canino", "cachorro", "labrador", "pastor", "bulldog", "poodle", "chihuahua", "husky", "doberman"],
            "gatos": ["gato", "felino", "gatito", "minino", "siames", "persa", "angora", "bengala", "maine coon", "ragdoll"],
            "salud": ["salud", "enfermedad", "síntoma", "veterinario", "vacuna", "desparasitación", 
                     "fiebre", "diarrea", "vómito", "alergia", "parásito", "infección", "dolor", "herida", "tratamiento"],
            "alimentacion": ["alimentación", "comida", "dieta", "nutrición", "pienso", "croquetas",
                           "premium", "balanceado", "suplemento", "vitamina", "obesidad", "peso", "ración", "alimento"],
            "cuidados": ["cuidados", "baño", "cepillado", "pelaje", "uñas", "orejas", "dientes",
                        "ejercicio", "paseo", "juego", "entrenamiento", "socialización", "higiene", "cepillo", "aseo"],
            "comportamiento": ["comportamiento", "conducta", "adiestramiento", "obediencia",
                             "agresividad", "ansiedad", "miedo", "ladrido", "maullido", "entrenar", "educar", "disciplina"],
            "emergencias": ["emergencia", "urgencia", "accidente", "envenenamiento", "trauma",
                           "sangrado", "fractura", "convulsión", "asfixia", "quemadura", "atropello", "golpe"],
            "razas": ["raza", "cruza", "mestizo", "pura sangre", "híbrido", "pedigrí", "características"],
            "reproduccion": ["cría", "reproducción", "embarazo", "parto", "esterilización", "castración", "cachorros", "gatitos", "gestación"]
        }
        
        self.palabras_emergencia = ["emergencia", "urgencia", "accidente", "envenenamiento", "sangrando", "asfixia", "convulsión", "fractura"]
        
        self.estadisticas = {
            "preguntas_totales": 0,
            "preguntas_validas": 0,
            "categorias": {},
            "tiempo_respuesta_promedio": 0,
            "errores": 0
        }

    def inicializar_historial(self):
        """Inicializa el historial de conversación"""
        return [
            {
                "role": "system", 
                "content": """Eres un veterinario experto y amable. Responde de forma concisa pero útil.
Mantén el contexto de la conversación y sé coherente con las preguntas anteriores.
Si es una emergencia, sé directo y claro sobre los pasos a seguir."""
            }
        ]

    def detectar_categoria(self, pregunta):
        """Detecta la categoría de la pregunta con mayor precisión"""
        pregunta_lower = pregunta.lower()
        
        # Detectar emergencias prioritariamente
        for palabra_emergencia in self.palabras_emergencia:
            if re.search(r'\b' + re.escape(palabra_emergencia) + r'\b', pregunta_lower):
                return "emergencia"
        
        categorias_detectadas = []
        for categoria, palabras in self.temas_mascotas.items():
            for palabra in palabras:
                if re.search(r'\b' + re.escape(palabra) + r'\b', pregunta_lower):
                    categorias_detectadas.append(categoria)
                    break
        
        return categorias_detectadas[0] if categorias_detectadas else "general"

    def es_tema_valido(self, pregunta):
        """Verifica si la pregunta es sobre mascotas con mayor precisión"""
        pregunta_lower = pregunta.lower()
        
        # Palabras clave generales de mascotas
        palabras_generales = ["mascota", "animal", "peludo", "dueño", "amo", "mascotas", "perro", "gato", "puppy", "kitten"]
        
        # Verificar en todas las categorías
        for categoria, palabras in self.temas_mascotas.items():
            for palabra in palabras:
                if re.search(r'\b' + re.escape(palabra) + r'\b', pregunta_lower):
                    return True, self.detectar_categoria(pregunta)
        
        # Verificar palabras generales
        for palabra in palabras_generales:
            if palabra in pregunta_lower:
                return True, "general"
                
        return False, None

    def generar_prompt_contextual(self, categoria, historial):
        """Genera prompts específicos para cada categoría considerando el historial"""
        prompts_base = {
            "emergencia": """Eres un veterinario de emergencias. Sé directo y claro.
Mantén el contexto de emergencias anteriores si es relevante.

Proporciona:
- 2-3 pasos de primeros auxilios inmediatos
- Cuándo acudir urgentemente al veterinario
- Qué evitar hacer

Máximo 80-100 palabras. Enfócate en lo esencial.""",

            "salud": """Eres un veterinario especialista. Sé práctico y preciso.
Considera el historial médico previo si está disponible.

Incluye:
- Posible causa principal
- 2-3 síntomas clave a observar
- Cuidados básicos inmediatos
- Señales para consultar al veterinario

Máximo 90-110 palabras. Información concisa pero completa.""",

            "alimentacion": """Eres un nutricionista veterinario. Recomendaciones específicas.
Considera preguntas anteriores sobre alimentación.

Incluye:
- 2-3 recomendaciones principales de alimentación
- Frecuencia y cantidades sugeridas
- Alimentos a evitar

Máximo 80-100 palabras. Sé práctico.""",

            "comportamiento": """Eres un etólogo veterinario. Soluciones prácticas.
Mantén coherencia con problemas de comportamiento mencionados antes.

Incluye:
- Causa probable del comportamiento
- 2-3 técnicas para corregirlo
- Tiempo esperado para ver resultados

Máximo 90-110 palabras. Enfoque positivo.""",

            "cuidados": """Eres un veterinario general. Cuidados básicos.
Considera el historial de cuidados mencionado.

Incluye:
- 3-4 cuidados esenciales
- Frecuencia recomendada
- Beneficios para la mascota

Máximo 70-90 palabras. Directo al punto.""",

            "general": """Eres un veterinario experimentado. Información útil.
Mantén la conversación fluida y coherente.

Proporciona:
- 3-4 puntos clave sobre el tema
- Recomendaciones prácticas
- Precauciones básicas

Máximo 80-100 palabras. Balanceado y claro."""
        }
        
        return prompts_base.get(categoria, prompts_base["general"])

    def generar_respuesta(self, pregunta, categoria, historial):
        """Genera respuesta usando OpenAI con contexto específico e historial"""
        try:
            start_time = time.time()
            
            # Actualizar el prompt del sistema con el contexto específico
            prompt_contextual = self.generar_prompt_contextual(categoria, historial)
            mensajes = historial.copy()
            mensajes[0] = {"role": "system", "content": prompt_contextual}
            
            # Agregar la nueva pregunta al historial
            mensajes.append({"role": "user", "content": pregunta})
            
            respuesta = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=mensajes,
                temperature=0.7,
                max_tokens=200,  # Aumentado ligeramente para mantener contexto
                top_p=0.9
            )
            
            respuesta_texto = respuesta.choices[0].message.content
            response_time = time.time() - start_time
            
            # Actualizar estadísticas
            self.actualizar_estadisticas(categoria, response_time)
            
            logger.info(f"Respuesta generada - Categoría: {categoria}, Tiempo: {response_time:.2f}s")
            return respuesta_texto, response_time
            
        except Exception as e:
            logger.error(f"Error en OpenAI: {str(e)}")
            self.estadisticas["errores"] += 1
            return "Lo siento, estoy teniendo dificultades técnicas. Por favor, intenta de nuevo.", 0

    def actualizar_estadisticas(self, categoria, tiempo_respuesta):
        """Actualiza las estadísticas del chatbot"""
        self.estadisticas["preguntas_totales"] += 1
        self.estadisticas["preguntas_validas"] += 1
        self.estadisticas["categorias"][categoria] = self.estadisticas["categorias"].get(categoria, 0) + 1
        
        # Calcular tiempo promedio de respuesta
        total_preguntas = self.estadisticas["preguntas_validas"]
        tiempo_actual = self.estadisticas["tiempo_respuesta_promedio"]
        self.estadisticas["tiempo_respuesta_promedio"] = (
            (tiempo_actual * (total_preguntas - 1) + tiempo_respuesta) / total_preguntas
        )

    def obtener_resumen_estadisticas(self):
        """Genera un resumen de las estadísticas"""
        if self.estadisticas["preguntas_validas"] == 0:
            return {
                "total_preguntas": 0,
                "preguntas_validas": 0,
                "categoria_mas_comun": "Ninguna",
                "tiempo_promedio_respuesta": 0,
                "distribucion_categorias": {},
                "errores": 0
            }
        
        categoria_mas_comun = max(self.estadisticas["categorias"].items(), key=lambda x: x[1])[0]
        
        return {
            "total_preguntas": self.estadisticas["preguntas_totales"],
            "preguntas_validas": self.estadisticas["preguntas_validas"],
            "categoria_mas_comun": categoria_mas_comun,
            "tiempo_promedio_respuesta": round(self.estadisticas["tiempo_respuesta_promedio"], 2),
            "distribucion_categorias": self.estadisticas["categorias"],
            "errores": self.estadisticas["errores"]
        }

# Instancia del chatbot
chatbot = VeterinarioChatbotAvanzado()

def responder_chatbot(pregunta, session):
    """Función principal para procesar preguntas con historial"""
    
    # Inicializar historial en la sesión si no existe
    if 'historial' not in session:
        session['historial'] = chatbot.inicializar_historial()
        session['conversacion_id'] = datetime.now().isoformat()
    
    # Verificar si es tema válido
    es_valido, categoria = chatbot.es_tema_valido(pregunta)
    
    if not es_valido:
        mensaje = """Hola, soy tu asistente veterinario virtual. 

Puedo ayudarte con:
- Salud de perros y gatos
- Alimentación y nutrición  
- Comportamiento y entrenamiento
- Emergencias veterinarias
- Cuidados básicos

¿En qué puedo ayudarte?"""
        return mensaje, 0, "saludo"
    
    # Generar respuesta con historial
    respuesta, tiempo_respuesta = chatbot.generar_respuesta(pregunta, categoria, session['historial'])
    
    # Actualizar historial en la sesión (limitar a últimos 10 mensajes para no exceder tokens)
    session['historial'].append({"role": "user", "content": pregunta})
    session['historial'].append({"role": "assistant", "content": respuesta})
    
    # Mantener solo los últimos 10 intercambios (20 mensajes) + el system prompt
    if len(session['historial']) > 21:  # 1 system + 20 mensajes (10 user + 10 assistant)
        session['historial'] = [session['historial'][0]] + session['historial'][-20:]
    
    # Guardar la sesión
    session.modified = True
    
    return respuesta, tiempo_respuesta, categoria

@app.route('/')
def index():
    # Inicializar sesión para nueva conversación
    session.clear()
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    pregunta = data.get('pregunta', '').strip()
    
    if not pregunta:
        return jsonify({
            'respuesta': 'Por favor, escribe una pregunta sobre mascotas.',
            'categoria': 'no_valida',
            'tiempo_respuesta': 0
        })
    
    # Procesar pregunta con historial
    respuesta, tiempo_respuesta, categoria = responder_chatbot(pregunta, session)
    
    return jsonify({
        'respuesta': respuesta,
        'categoria': categoria,
        'tiempo_respuesta': round(tiempo_respuesta, 2),
        'conversacion_id': session.get('conversacion_id', '')
    })

@app.route('/nueva_conversacion', methods=['POST'])
def nueva_conversacion():
    """Endpoint para iniciar una nueva conversación"""
    session.clear()
    session['historial'] = chatbot.inicializar_historial()
    session['conversacion_id'] = datetime.now().isoformat()
    session.modified = True
    
    return jsonify({
        'status': 'success',
        'mensaje': 'Nueva conversación iniciada',
        'conversacion_id': session['conversacion_id']
    })

@app.route('/estadisticas_conversacion')
def estadisticas_conversacion():
    """Endpoint para obtener estadísticas de la conversación actual"""
    historial = session.get('historial', [])
    mensajes_usuario = [msg for msg in historial if msg['role'] == 'user']
    
    return jsonify({
        'conversacion_id': session.get('conversacion_id', ''),
        'total_mensajes': len(historial) - 1,  # Excluye system prompt
        'total_preguntas': len(mensajes_usuario),
        'historial_reciente': [msg['content'] for msg in historial[-6:]]  # Últimos 3 intercambios
    })

@app.route('/estadisticas')
def obtener_estadisticas():
    """Endpoint para obtener estadísticas completas"""
    return jsonify(chatbot.obtener_resumen_estadisticas())

@app.route('/categorias')
def obtener_categorias():
    """Endpoint para obtener las categorías disponibles"""
    return jsonify({
        "categorias_disponibles": list(chatbot.temas_mascotas.keys()),
        "total_temas_reconocidos": sum(len(palabras) for palabras in chatbot.temas_mascotas.values())
    })

@app.route('/health')
def health_check():
    """Endpoint para verificar el estado del servicio"""
    return jsonify({
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "version": "2.1.0",
        "sesion_activa": 'historial' in session
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)