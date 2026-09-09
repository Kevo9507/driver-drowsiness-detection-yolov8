from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route("/")
def index():
    evento = "Normal"
    imagen = None
    hora = ""
    nivel = "Normal"

    try:
        with open("ultimo_evento.txt", "r") as f:
            contenido = f.read().strip()
            partes = contenido.split("|")

            if len(partes) >= 4:
                evento, imagen, hora, nivel = partes

                # Solo mostramos imagen si es evento importante
                if not any(e in evento.upper() for e in ["DORMIDO", "MICROSUEÑO", "BOSTEZO"]):
                    imagen = None
            elif len(partes) == 3:
                evento, imagen, hora = partes
                if not any(e in evento.upper() for e in ["DORMIDO", "MICROSUEÑO", "BOSTEZO"]):
                    imagen = None
    except FileNotFoundError:
        pass

    return render_template("index.html", evento=evento, imagen=imagen, hora=hora, nivel=nivel)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
