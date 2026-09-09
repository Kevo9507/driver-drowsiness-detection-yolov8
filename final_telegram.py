import cv2
from ultralytics import YOLO
import os
from datetime import datetime
import time
import requests  # Para enviar mensajes por Telegram

# ⚙️ Configuración de Telegram
TELEGRAM_TOKEN = "7128105026:AAFBsU_FQhXr9fXnp9eF5QQLE4Ad2K5XqAo"
TELEGRAM_CHAT_ID = "565648492"

def enviar_mensaje_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}
    try:
        requests.post(url, data=data)
        print(f"📤 Mensaje enviado por Telegram: {mensaje}")
    except Exception as e:
        print(f"⚠️ Error enviando mensaje por Telegram: {e}")

# Cargar el modelo
model = YOLO("best.pt")

# Crear carpeta de salida
os.makedirs("static/eventos", exist_ok=True)

# Pipeline cámara Jetson
gst = (
    "nvarguscamerasrc ! "
    "video/x-raw(memory:NVMM), width=640, height=480, format=NV12, framerate=30/1 ! "
    "nvvidconv ! "
    "video/x-raw, format=BGRx ! videoconvert ! "
    "video/x-raw, format=BGR ! appsink"
)

cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)
if not cap.isOpened():
    print("❌ No se pudo abrir la cámara.")
    exit()

print("✅ Cámara abierta y modelo cargado correctamente")

# Variables de control
inicio_ojos_cerrados = None
inicio_comb_dormido = None
inicio_bostezo = None
tiempos_ojos_cerrados = []

# Cooldowns
cooldown_general = 5
cooldowns_eventos = {
    "MICROSUEÑO": 60,
    "DORMIDO": 60,
    "DORMIDO_CON_BOCA_ABIERTA": 5,
    "BOSTEZO": 30
}
ultimos_guardados = {k: 0 for k in cooldowns_eventos}

# Parámetros
duracion_microsueño_min = 3
duracion_microsueño_max = 10
duracion_dormido = 10
duracion_bostezo = 1  # segundos de boca abierta continua
ventana_perclos = 60  # segundos
fps_estimado = 30
evento_previo = None
nivel_somnolencia = "Normal"

while True:
    ret, frame = cap.read()
    if not ret:
        break

    ahora = time.time()
    results = model(frame, imgsz=640, conf=0.5)[0]
    clases_detectadas = [results.names[int(box.cls)] for box in results.boxes]

    ojos_cerrados = 'ojos-cerrados' in clases_detectadas
    boca_abierta = 'boca_abierta' in clases_detectadas

    evento = None

    # Calcular PERCLOS
    if ojos_cerrados:
        tiempos_ojos_cerrados.append(ahora)
    tiempos_ojos_cerrados = [t for t in tiempos_ojos_cerrados if ahora - t <= ventana_perclos]
    perclos = len(tiempos_ojos_cerrados) / (ventana_perclos * fps_estimado)

    if perclos > 0.4:
        nivel_somnolencia = "SOMNOLENCIA ALTA"
        color_nivel = (0, 0, 255)
    elif perclos > 0.2:
        nivel_somnolencia = "SOMNOLENCIA LEVE"
        color_nivel = (0, 165, 255)
    else:
        nivel_somnolencia = "Normal"
        color_nivel = (0, 255, 0)

    # Evento: ojos cerrados por cierto tiempo
    if ojos_cerrados and not boca_abierta:
        if inicio_ojos_cerrados is None:
            inicio_ojos_cerrados = ahora
        tiempo_cerrado = ahora - inicio_ojos_cerrados

        if duracion_microsueño_min <= tiempo_cerrado < duracion_microsueño_max:
            evento = "MICROSUEÑO"
        elif tiempo_cerrado >= duracion_dormido:
            evento = "DORMIDO"
    else:
        inicio_ojos_cerrados = None

    # Evento: dormido con boca abierta
    if ojos_cerrados and boca_abierta:
        if inicio_comb_dormido is None:
            inicio_comb_dormido = ahora
        if ahora - inicio_comb_dormido >= 8:
            evento = "DORMIDO_CON_BOCA_ABIERTA"
    else:
        inicio_comb_dormido = None

    # Evento: BOSTEZO sostenido
    if boca_abierta:
        if inicio_bostezo is None:
            inicio_bostezo = ahora
        elif ahora - inicio_bostezo >= duracion_bostezo:
            evento = "BOSTEZO"
    else:
        inicio_bostezo = None

    # Guardar imagen si hay evento nuevo y cooldown cumplido
    if evento:
        cooldown_evento = cooldowns_eventos.get(evento, cooldown_general)
        if ahora - ultimos_guardados.get(evento, 0) > cooldown_evento:
            nombre_archivo = f"{evento}{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            ruta = os.path.join("static/eventos", nombre_archivo)
            cv2.imwrite(ruta, frame)
            print(f"📸 Imagen guardada: {ruta}")
            ultimos_guardados[evento] = ahora
            evento_previo = ahora

            try:
                with open("ultimo_evento.txt", "w") as f:
                    f.write(f"{evento}|{nombre_archivo}|{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}|{nivel_somnolencia}")
            except Exception as e:
                print(f"⚠️ Error guardando evento: {e}")

            # Enviar mensaje por Telegram
            mensaje = f"🚨 Evento detectado: {evento}\n🕒 {datetime.now().strftime('%H:%M:%S')}\n😴 Nivel: {nivel_somnolencia}"
            enviar_mensaje_telegram(mensaje)

    # Estado "normal" si no hay eventos recientes
    elif evento_previo and ahora - evento_previo > 60:
        try:
            with open("ultimo_evento.txt", "w") as f:
                f.write(f"Normal||{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}|{nivel_somnolencia}")
            evento_previo = None
        except Exception as e:
            print(f"⚠️ Error escribiendo estado normal: {e}")

    # Mostrar resultados
    annotated = results.plot()
    cv2.putText(annotated, f"Nivel: {nivel_somnolencia}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_nivel, 2)
    cv2.putText(annotated, f"PERCLOS: {perclos:.2f}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    cv2.imshow("Detección de Somnolencia", annotated)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
