# JOSÉ NOGUERA REYES

from flask import Flask, request, jsonify, Response
import psycopg2
import psycopg2.extras
import xml.etree.ElementTree as ET

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Configuración de la conexión a la base de datos
DB_CONFIG = {
    "dbname": "apitasks",
    "user": "postgres",
    "password": "12345678",
    "host": "localhost",
    "port": "5432"
}

def get_connection():  # Conectar a la base de datos
    return psycopg2.connect(**DB_CONFIG)

# Clase Task ----------------------
class Task:

    @staticmethod
    def validar_datos(data):  # Validar los datos de la tarea
        if not data:
            return "Datos no proporcionados."
        if 'title' not in data:
            return "El campo 'title' es obligatorio."
        if 'description' not in data:
            return "El campo 'description' es obligatorio."
        if 'completed' not in data:
            return "El campo 'completed' es obligatorio."
        if not isinstance(data['completed'], bool):
            return "El campo 'completed' debe ser un booleano."
        return None

# Parsear XML del body y convertirlo a dict
def parse_xml_request(req):
    if req.content_type == "application/xml":
        try:
            tree = ET.fromstring(req.data)
            data = {child.tag: child.text for child in tree}
            # Convertir "completed" de string a bool
            if "completed" in data:
                data["completed"] = data["completed"].lower() == "true"
            return data
        except Exception:
            return None
    return None

# Convertir lista/dict a XML
def dict_to_xml(tag, d):
    elem = ET.Element(tag)
    for key, val in d.items():
        child = ET.SubElement(elem, key)
        child.text = str(val).lower() if isinstance(val, bool) else str(val)
    return elem

def list_to_xml(tag, l):
    elem = ET.Element(tag)
    for item in l:
        elem.append(dict_to_xml("task", item))
    return elem

def to_response(data, status=200):
    """ Devuelve respuesta en JSON o XML según Accept """
    accept = request.headers.get("Accept", "application/json")
    if "application/xml" in accept:
        if isinstance(data, list):
            xml_data = list_to_xml("tasks", data)
        else:
            xml_data = dict_to_xml("task", data)
        return Response(ET.tostring(xml_data, encoding="utf-8"), mimetype="application/xml", status=status)
    return jsonify(data), status

# ENDPOINTS --------------------

# GET
@app.route('/tasks', methods=['GET']) # Obtener TODAS las tareas
def get_tasks():
    completed = request.args.get("completed")
    search = request.args.get("search")

    query = "SELECT id, title, description, completed FROM tasks"
    conditions = []
    params = []

    if completed is not None:
        conditions.append("completed = %s")
        params.append(completed.lower() == "true")

    if search:
        conditions.append("(title ILIKE %s OR description ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id;"

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    tasks = [dict(row) for row in rows]
    return to_response(tasks, 200)

@app.route('/tasks/<int:id_task>', methods=['GET']) # Obtener una tarea específica
def get_task(id_task):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT id, title, description, completed FROM tasks WHERE id = %s;", (id_task,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return to_response({"error": "Tarea no encontrada."}, 404)

    return to_response(dict(row), 200)

# MÉTODO POST
@app.route('/tasks', methods=['POST'])
def crear_task():
    if request.content_type == "application/xml":
        data = parse_xml_request(request)
    else:
        data = request.get_json(silent=True)
    if not data:
        return to_response({"error": "Formato de datos no soportado o inválido"}, 400)

    error = Task.validar_datos(data)
    if error:
        return to_response({"error": error}, 400)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        "INSERT INTO tasks (title, description, completed) VALUES (%s, %s, %s) RETURNING *;",
        (data['title'], data['description'], data['completed'])
    )
    new_task = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return to_response(dict(new_task), 201)

# MÉTODO PUT
@app.route('/tasks/<int:id_task>', methods=['PUT'])
def actualizar_task(id_task):
    if request.content_type == "application/xml":
        data = parse_xml_request(request)
    else:
        data = request.get_json(silent=True)
    if not data:
        return to_response({"error": "Formato de datos no soportado o inválido"}, 400)

    error = Task.validar_datos(data)
    if error:
        return to_response({"error": error}, 400)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Verificar si la tarea existe
    cur.execute("SELECT id FROM tasks WHERE id = %s;", (id_task,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        return to_response({"error": "Tarea no encontrada."}, 404)

    # Actualizar
    cur.execute(
        "UPDATE tasks SET title = %s, description = %s, completed = %s WHERE id = %s RETURNING *;",
        (data['title'], data['description'], data['completed'], id_task)
    )
    updated_task = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return to_response(dict(updated_task), 200)

# MÉTODO DELETE
@app.route('/tasks/<int:id_task>', methods=['DELETE'])
def borrar_task(id_task):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("DELETE FROM tasks WHERE id = %s RETURNING *;", (id_task,))
    deleted_task = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if not deleted_task:
        return to_response({"error": "Tarea no encontrada."}, 404)

    return to_response({"message": "Tarea eliminada correctamente."}, 200)

# MANEJO DE ERRORES -----------------
@app.errorhandler(404)
def no_encontrado(error):
    return jsonify({'error': 'Endpoint no encontrado.'}), 404

@app.errorhandler(500)
def error_interno(error):
    return jsonify({'error': 'Error interno del servidor.'}), 500

# EJECUCIÓN -------------------------
if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)