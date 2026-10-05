"""Biblioteca Horizonte - MVP de reservas (Flask + SQLite)."""
import os
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE, "static"))
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "clave-solo-para-desarrollo")
app.config["DB_PATH"] = os.environ.get("DB_PATH", os.path.join(BASE, "biblioteca.db"))

# Módulos horarios completos (supuesto del equipo, editable).
MODULOS = {
    1: "07:30 - 08:30", 2: "08:30 - 09:30", 3: "09:40 - 10:40",
    4: "10:40 - 11:40", 5: "11:50 - 12:50", 6: "12:50 - 13:50",
}
MENSAJES = {
    "PENDIENTE": "Pendiente: todavía NO está confirmada. Lucía debe revisarla.",
    "CONFIRMADA": "Confirmada: el recurso es tuyo para esa fecha y módulo.",
    "RECHAZADA": "Rechazada: el recurso no fue asignado. Podés pedir otro módulo o recurso.",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, usuario TEXT NOT NULL UNIQUE,
  clave_hash TEXT NOT NULL, rol TEXT NOT NULL CHECK (rol IN ('DOCENTE','BIBLIOTECARIA')));
CREATE TABLE IF NOT EXISTS recursos (
  id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, tipo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS solicitudes (
  id INTEGER PRIMARY KEY,
  docente_id INTEGER NOT NULL REFERENCES usuarios(id),
  recurso_id INTEGER NOT NULL REFERENCES recursos(id),
  fecha TEXT NOT NULL, modulo INTEGER NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('PENDIENTE','CONFIRMADA','RECHAZADA')),
  creada_en TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS historial (
  id INTEGER PRIMARY KEY, solicitud_id INTEGER NOT NULL REFERENCES solicitudes(id),
  estado TEXT NOT NULL, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
  fecha_hora TEXT NOT NULL);
-- Regla central, garantizada también por la base de datos:
CREATE UNIQUE INDEX IF NOT EXISTS uq_una_confirmada
  ON solicitudes(recurso_id, fecha, modulo) WHERE estado = 'CONFIRMADA';
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(app.config["DB_PATH"])
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        usuarios = [("Lucía (bibliotecaria)", "lucia", "lucia123", "BIBLIOTECARIA"),
                    ("Ana Pérez", "ana", "ana123", "DOCENTE"),
                    ("Marcos Díaz", "marcos", "marcos123", "DOCENTE"),
                    ("Sofía Ruiz", "sofia", "sofia123", "DOCENTE")]
        db.executemany("INSERT INTO usuarios(nombre,usuario,clave_hash,rol) VALUES (?,?,?,?)",
                       [(n, u, generate_password_hash(c), r) for n, u, c, r in usuarios])
        recursos = [(f"Proyector {i}", "PROYECTOR") for i in (1, 2)]
        recursos += [(f"Notebook {i}", "NOTEBOOK") for i in (1, 2, 3, 4)]
        db.executemany("INSERT INTO recursos(nombre,tipo) VALUES (?,?)", recursos)
    db.commit()
    db.close()


# ---------- utilidades ----------
def error(msg, code):
    return jsonify({"error": msg}), code


def requiere(rol=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "uid" not in session:
                return error("Tenés que iniciar sesión.", 401)
            if rol and session.get("rol") != rol:
                return error("No tenés permiso para esta operación.", 403)
            return fn(*a, **kw)
        return wrapper
    return deco


def ahora():
    return datetime.now().isoformat(timespec="seconds")


def fila_a_dict(r):
    d = dict(r)
    d["modulo_horario"] = MODULOS.get(d["modulo"], "")
    d["mensaje"] = MENSAJES[d["estado"]]
    return d


SELECT_SOL = """SELECT s.id, s.fecha, s.modulo, s.estado, s.creada_en,
  s.recurso_id, r.nombre AS recurso, s.docente_id, u.nombre AS docente
  FROM solicitudes s JOIN recursos r ON r.id = s.recurso_id
  JOIN usuarios u ON u.id = s.docente_id"""


def registrar(db, sid, estado):
    db.execute("INSERT INTO historial(solicitud_id,estado,usuario_id,fecha_hora) VALUES (?,?,?,?)",
               (sid, estado, session["uid"], ahora()))


# ---------- sesión ----------
@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    u = get_db().execute("SELECT * FROM usuarios WHERE usuario = ?",
                         (str(d.get("usuario", "")).strip().lower(),)).fetchone()
    if not u or not check_password_hash(u["clave_hash"], str(d.get("clave", ""))):
        return error("Usuario o clave incorrectos.", 401)
    session.clear()
    session["uid"], session["rol"], session["nombre"] = u["id"], u["rol"], u["nombre"]
    return jsonify({"id": u["id"], "nombre": u["nombre"], "rol": u["rol"]})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/yo")
@requiere()
def yo():
    return jsonify({"id": session["uid"], "nombre": session["nombre"], "rol": session["rol"]})


# ---------- datos ----------
@app.get("/api/recursos")
@requiere()
def recursos():
    rows = get_db().execute("SELECT id, nombre, tipo FROM recursos ORDER BY id").fetchall()
    return jsonify({"recursos": [dict(r) for r in rows],
                    "modulos": [{"id": k, "horario": v} for k, v in MODULOS.items()]})


@app.post("/api/solicitudes")
@requiere("DOCENTE")
def crear_solicitud():
    d = request.get_json(silent=True) or {}
    db = get_db()
    try:
        recurso_id, modulo = int(d.get("recurso_id")), int(d.get("modulo"))
    except (TypeError, ValueError):
        return error("Elegí un recurso y un módulo horario.", 400)
    if not db.execute("SELECT 1 FROM recursos WHERE id = ?", (recurso_id,)).fetchone():
        return error("El recurso no existe.", 400)
    if modulo not in MODULOS:
        return error("El módulo horario no es válido.", 400)
    try:
        fecha = date.fromisoformat(str(d.get("fecha", "")))
    except ValueError:
        return error("La fecha es obligatoria y debe ser válida (AAAA-MM-DD).", 400)
    if fecha < date.today():
        return error("La fecha no puede ser anterior a hoy.", 400)
    if db.execute("""SELECT 1 FROM solicitudes WHERE docente_id=? AND recurso_id=? AND fecha=?
                     AND modulo=? AND estado='PENDIENTE'""",
                  (session["uid"], recurso_id, fecha.isoformat(), modulo)).fetchone():
        return error("Ya tenés una solicitud pendiente igual a esta.", 409)
    with db:
        cur = db.execute("""INSERT INTO solicitudes(docente_id,recurso_id,fecha,modulo,estado,creada_en)
                            VALUES (?,?,?,?,'PENDIENTE',?)""",
                         (session["uid"], recurso_id, fecha.isoformat(), modulo, ahora()))
        registrar(db, cur.lastrowid, "PENDIENTE")
    r = db.execute(SELECT_SOL + " WHERE s.id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(fila_a_dict(r)), 201


@app.get("/api/solicitudes")
@requiere()
def listar_solicitudes():
    sql, args = SELECT_SOL + " WHERE 1=1", []
    if session["rol"] == "DOCENTE":  # un docente solo ve las suyas
        sql += " AND s.docente_id = ?"
        args.append(session["uid"])
    for campo, col in (("estado", "s.estado"), ("recurso_id", "s.recurso_id"), ("fecha", "s.fecha")):
        if request.args.get(campo):
            sql += f" AND {col} = ?"
            args.append(request.args[campo])
    rows = get_db().execute(sql + " ORDER BY s.id DESC", args).fetchall()
    return jsonify([fila_a_dict(r) for r in rows])


def resolver(sid, nuevo):
    db = get_db()
    s = db.execute("SELECT * FROM solicitudes WHERE id = ?", (sid,)).fetchone()
    if not s:
        return error("La solicitud no existe.", 404)
    if s["estado"] != "PENDIENTE":
        return error(f"La solicitud ya está {s['estado'].lower()}; no se puede cambiar.", 409)
    try:
        with db:
            db.execute("UPDATE solicitudes SET estado = ? WHERE id = ?", (nuevo, sid))
            registrar(db, sid, nuevo)
    except sqlite3.IntegrityError:
        return error("Ya existe una reserva CONFIRMADA para ese recurso, fecha y módulo.", 409)
    return jsonify(fila_a_dict(db.execute(SELECT_SOL + " WHERE s.id = ?", (sid,)).fetchone()))


@app.post("/api/solicitudes/<int:sid>/confirmar")
@requiere("BIBLIOTECARIA")
def confirmar(sid):
    return resolver(sid, "CONFIRMADA")


@app.post("/api/solicitudes/<int:sid>/rechazar")
@requiere("BIBLIOTECARIA")
def rechazar(sid):
    return resolver(sid, "RECHAZADA")


@app.get("/api/solicitudes/<int:sid>/historial")
@requiere()
def historial(sid):
    db = get_db()
    s = db.execute("SELECT docente_id FROM solicitudes WHERE id = ?", (sid,)).fetchone()
    if not s or (session["rol"] == "DOCENTE" and s["docente_id"] != session["uid"]):
        return error("La solicitud no existe.", 404)
    rows = db.execute("""SELECT h.estado, h.fecha_hora, u.nombre AS usuario FROM historial h
                         JOIN usuarios u ON u.id = h.usuario_id
                         WHERE h.solicitud_id = ? ORDER BY h.id""", (sid,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/reservas")
@requiere()
def reservas():
    sql = SELECT_SOL + " WHERE s.estado = 'CONFIRMADA'"
    args = []
    for campo, col in (("recurso_id", "s.recurso_id"), ("fecha", "s.fecha")):
        if request.args.get(campo):
            sql += f" AND {col} = ?"
            args.append(request.args[campo])
    rows = get_db().execute(sql + " ORDER BY s.fecha, s.modulo", args).fetchall()
    return jsonify([fila_a_dict(r) for r in rows])


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


init_db()

if __name__ == "__main__":
    app.run(debug=False, port=5000)
